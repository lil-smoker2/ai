"""Net worth service: price what the user owns and keep it recorded.

Two rules carry through everything here:

* Every figure is *derived* from inventory records. The user never enters a
  net worth, so it cannot drift out of step with what they actually own.
* A hole is reported as unknown, never papered over with zero. If an owned
  item has no price, the total is null and the page says how many items are
  still unpriced - the partial sum stays available as "at least this much".

Pictures come from the same folder matcher the gallery endpoints use, so a
"Trousers" item resolves the images filed under ``clothing/trousers``.
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.inventory import InventoryCategory, InventoryItem
from app.models.user import User
from app.models.valuation import NetWorthSnapshot
from app.schemas.valuation import NetWorthSaved, Valuation, ValuationLine
from app.services import trend as trend_service
from app.services.asset_scanner import category_match

HISTORY_LIMIT = 12
NOTE = (
    "Net worth is the value of what you own, calculated from your inventory. "
    "It is saved automatically whenever your items or prices change. Items "
    "without a price are counted separately - never assumed to be free."
)


def slugify(name: str | None) -> str | None:
    """Inventory category name -> asset folder label ("Trousers" -> "trousers")."""
    if not name:
        return None
    slug = "-".join(name.strip().lower().split())
    return slug or None


@dataclass
class Summary:
    """The totals behind both the page and the saved snapshot."""

    items: int = 0
    units_owned: int = 0
    units_needed: int = 0
    net_worth_minor: int | None = None
    priced_value_minor: int = 0
    valued_items: int = 0
    unpriced_items: int = 0
    to_target_minor: int | None = None
    replacement_total_minor: int | None = None


def _asset_ids(db: Session, label: str, cache: dict[str, list[str]]) -> list[str]:
    if label not in cache:
        match = category_match(label)
        ids = (
            []
            if match is None
            else list(
                db.scalars(
                    select(Asset.id)
                    .where(Asset.status == "active", match)
                    .order_by(Asset.rel_path)
                ).all()
            )
        )
        cache[label] = ids
    return cache[label]


def _photo(
    db: Session, item: InventoryItem, label: str, cache: dict[str, list[str]]
) -> str | None:
    """The item's own picture if it has one, else a stable match by category.

    ``item_id % n`` keeps the choice deterministic - the same item never flips
    between two pictures from one request to the next.
    """
    if item.image_asset_id:
        pinned = db.get(Asset, item.image_asset_id)
        if pinned is not None and pinned.status == "active":
            return pinned.id
    ids = _asset_ids(db, label, cache) if label else []
    return ids[item.id % len(ids)] if ids else None


def compute_lines(db: Session, user: User) -> list[ValuationLine]:
    items = db.scalars(
        select(InventoryItem)
        .where(InventoryItem.user_id == user.id, InventoryItem.deleted_at.is_(None))
        .order_by(InventoryItem.name)
    ).all()
    names = {
        c.id: c.name
        for c in db.scalars(
            select(InventoryCategory).where(InventoryCategory.user_id == user.id)
        ).all()
    }
    cache: dict[str, list[str]] = {}

    lines: list[ValuationLine] = []
    for item in items:
        category_name = names.get(item.category_id)
        label = slugify(category_name)
        needed = (
            max(item.target_quantity - item.quantity_owned, 0)
            if item.target_quantity is not None
            else 0
        )
        price = item.estimated_unit_cost_minor
        owned = item.quantity_owned

        # Nothing owned contributes nothing, priced or not; something owned
        # without a price makes the value unknown.
        if price is not None:
            value = owned * price
        else:
            value = 0 if owned == 0 else None
        if price is not None:
            to_target = needed * price
        else:
            to_target = 0 if needed == 0 else None

        lines.append(
            ValuationLine(
                item_id=item.id,
                name=item.name,
                category_name=category_name,
                category_slug=label,
                quantity_owned=owned,
                unit=item.unit,
                target_quantity=item.target_quantity,
                needed_quantity=needed,
                unit_cost_minor=price,
                price_verified=bool(item.price_verified),
                value_minor=value,
                to_target_minor=to_target,
                price_needed=price is None and (owned > 0 or needed > 0),
                image_asset_id=_photo(db, item, label, cache),
            )
        )
    return lines


def summarise(lines: list[ValuationLine]) -> Summary:
    s = Summary(items=len(lines))
    to_target_known = True
    for line in lines:
        s.units_owned += line.quantity_owned
        s.units_needed += line.needed_quantity
        if line.value_minor is None:
            s.unpriced_items += 1
        else:
            s.priced_value_minor += line.value_minor
            if line.unit_cost_minor is not None:
                s.valued_items += 1
        if line.to_target_minor is None:
            to_target_known = False

    # An unpriced item you own makes the worth unknown, not understated.
    s.net_worth_minor = None if s.unpriced_items else s.priced_value_minor
    s.to_target_minor = (
        sum(line.to_target_minor or 0 for line in lines) if to_target_known else None
    )
    if s.net_worth_minor is not None and s.to_target_minor is not None:
        s.replacement_total_minor = s.net_worth_minor + s.to_target_minor
    return s


def record(db: Session, user: User) -> NetWorthSnapshot:
    """Save (or refresh) today's valuation. Callers commit with their change,
    so a saved figure and the edit that produced it land in one transaction."""
    # Sessions here do not autoflush, and an unflushed delete would still be
    # selected below - a soft-deleted item would keep its value on the books.
    db.flush()
    s = summarise(compute_lines(db, user))
    today = date.today()
    snapshot = db.scalar(
        select(NetWorthSnapshot).where(
            NetWorthSnapshot.user_id == user.id, NetWorthSnapshot.on_date == today
        )
    )
    if snapshot is None:
        snapshot = NetWorthSnapshot(user_id=user.id, on_date=today)
        db.add(snapshot)
    snapshot.net_worth_minor = s.net_worth_minor
    snapshot.priced_value_minor = s.priced_value_minor
    snapshot.valued_items = s.valued_items
    snapshot.unpriced_items = s.unpriced_items
    snapshot.complete = s.unpriced_items == 0
    db.flush()
    return snapshot


def latest(db: Session, user: User) -> NetWorthSnapshot | None:
    return db.scalar(
        select(NetWorthSnapshot)
        .where(NetWorthSnapshot.user_id == user.id)
        .order_by(NetWorthSnapshot.on_date.desc(), NetWorthSnapshot.id.desc())
        .limit(1)
    )


def saved_net_worth(db: Session, user: User) -> int | None:
    """The recorded figure for other screens (dashboard), null when unknown."""
    snapshot = latest(db, user)
    return snapshot.net_worth_minor if snapshot else None


def _out(snapshot: NetWorthSnapshot) -> NetWorthSaved:
    return NetWorthSaved(
        on_date=snapshot.on_date,
        net_worth_minor=snapshot.net_worth_minor,
        priced_value_minor=snapshot.priced_value_minor,
        valued_items=snapshot.valued_items,
        unpriced_items=snapshot.unpriced_items,
        complete=snapshot.complete,
        updated_at=snapshot.updated_at,
    )


def valuation(db: Session, user: User) -> Valuation:
    lines = compute_lines(db, user)
    s = summarise(lines)

    snapshot = db.scalar(
        select(NetWorthSnapshot).where(
            NetWorthSnapshot.user_id == user.id,
            NetWorthSnapshot.on_date == date.today(),
        )
    )
    if snapshot is None:
        # First look at this day's worth: record it now, so the page reports a
        # saved figure rather than one that only exists while it is open.
        snapshot = record(db, user)
        db.commit()

    history = db.scalars(
        select(NetWorthSnapshot)
        .where(NetWorthSnapshot.user_id == user.id)
        .order_by(NetWorthSnapshot.on_date.desc(), NetWorthSnapshot.id.desc())
        .limit(HISTORY_LIMIT)
    ).all()

    return Valuation(
        currency=user.currency,
        lines=lines,
        items=s.items,
        units_owned=s.units_owned,
        units_needed=s.units_needed,
        net_worth_minor=s.net_worth_minor,
        priced_value_minor=s.priced_value_minor,
        valued_items=s.valued_items,
        unpriced_items=s.unpriced_items,
        to_target_minor=s.to_target_minor,
        replacement_total_minor=s.replacement_total_minor,
        saved=_out(snapshot),
        history=[_out(row) for row in history],
        # Reads the same snapshots the table shows; None when they are too few.
        trend=trend_service.describe(db, user),
        note=NOTE,
    )
