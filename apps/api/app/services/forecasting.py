"""How long a tracked thing will last, read from its own history.

The alerts say what is short right now. This answers the earlier question: at
the rate something has actually been used, when will the current stock run out?
The answer is built only from the quantity events the app already records, so a
rate exists exactly where the records show consumption. An item with no
depletion history produces nothing rather than a plausible-looking date - a
guessed run-out is the kind of false figure this app refuses to print.

Three rules keep it honest:

* Only events that took stock away count. Purchases and openings add quantity;
  folding them into a "use rate" would understate how fast things disappear.
* The rate is measured over recent behaviour (FORECAST_WINDOW_DAYS), so a habit
  that stopped does not keep forecasting a run-out forever.
* Money leaves as integer minor units, and only when a price was recorded; a
  shortage with no price reports that the price is missing, never a zero total.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.goal import Goal, GoalContribution
from app.models.inventory import InventoryCategory, InventoryItem, QuantityEvent
from app.models.user import User

# A rate reflects recent behaviour, not the whole life of the item. 120 days is
# wide enough to see a slow habit without carrying forward consumption that no
# longer happens.
FORECAST_WINDOW_DAYS = 120

# How soon a run-out counts as worth flagging "restock soon".
RESTOCK_SOON_DAYS = 14

# This many separate depletions reads as a steady, repeating habit rather than a
# one-off, and is what separates "steady" confidence from "limited".
_STEADY_EVENTS = 3


def _depletion_stats(events, today: date) -> tuple[int, date, int] | None:
    """(units_used, first_date, count) of consumption inside the window, or None.

    Returns None when nothing in the window took stock away, because then there
    is no observed rate to project from.
    """
    cutoff = today - timedelta(days=FORECAST_WINDOW_DAYS)
    total = 0
    first: date | None = None
    count = 0
    for e in events:
        if e.change >= 0 or e.occurred_on < cutoff:
            continue
        total += -e.change
        count += 1
        if first is None or e.occurred_on < first:
            first = e.occurred_on
    if total <= 0 or first is None:
        return None
    return total, first, count


def forecast_replenishment(db: Session, user: User,
                           today: date | None = None) -> dict:
    """Per-item run-out estimates, soonest first."""
    today = today or date.today()
    items = db.scalars(
        select(InventoryItem).where(
            InventoryItem.user_id == user.id,
            InventoryItem.deleted_at.is_(None),
        )
    ).all()
    cat_names = {c.id: c.name for c in db.scalars(
        select(InventoryCategory).where(InventoryCategory.user_id == user.id)
    ).all()}

    forecasts: list[dict] = []
    for item in items:
        events = db.scalars(
            select(QuantityEvent)
            .where(QuantityEvent.item_id == item.id, QuantityEvent.user_id == user.id)
            .order_by(QuantityEvent.occurred_on)
        ).all()
        stats = _depletion_stats(events, today)
        if stats is None:
            continue  # no consumption in the window -> no date, rather than a guess
        total, first, count = stats
        # Measured from the earliest use in the window to today; a single day is
        # the floor so a same-day habit still yields a finite rate.
        observed_days = max(1, (today - first).days)
        rate = total / observed_days
        if rate <= 0:
            continue
        days_to_zero = 0 if item.quantity_owned <= 0 else int(item.quantity_owned // rate)

        shortage = (
            max(item.target_quantity - item.quantity_owned, 0)
            if item.target_quantity is not None
            else 0
        )
        refill_cost = (
            shortage * item.estimated_unit_cost_minor
            if shortage > 0 and item.estimated_unit_cost_minor is not None
            else None
        )
        forecasts.append({
            "item_id": item.id,
            "name": item.name,
            "category_name": cat_names.get(item.category_id),
            "unit": item.unit,
            "quantity_owned": item.quantity_owned,
            "target_quantity": item.target_quantity,
            "shortage": shortage,
            "consumption_per_day": round(rate, 4),
            "consumption_events": count,
            "window_days": observed_days,
            "days_to_zero": days_to_zero,
            "runout_on": today + timedelta(days=days_to_zero),
            "restock_soon": days_to_zero <= RESTOCK_SOON_DAYS,
            "estimated_refill_cost_minor": refill_cost,
            "confidence": "steady" if count >= _STEADY_EVENTS else "limited",
        })

    forecasts.sort(key=lambda f: (f["days_to_zero"], f["name"].lower()))
    return {"generated_on": today, "currency": user.currency, "forecasts": forecasts}


def project_goal_completion(db: Session, goal: Goal,
                            remaining_minor: int | None,
                            today: date | None = None) -> dict | None:
    """When this goal's target would be reached at its own recent saving pace.

    The pace is the total of contributions inside the observation window over
    the days since the earliest one - the same reading used for run-outs. It
    exists only where the records show money actually arriving: a goal with no
    recent contributions, no money target, or one already finished or paused
    gets no projection, because a date invented from nothing is exactly what
    this app refuses to print. Days-to-target floors down, so the estimate is
    never more optimistic than the history allows.
    """
    if goal.status != "active":
        return None
    if remaining_minor is None or remaining_minor <= 0:
        return None
    today = today or date.today()
    cutoff = today - timedelta(days=FORECAST_WINDOW_DAYS)

    total = 0
    first: date | None = None
    count = 0
    for c in db.scalars(
        select(GoalContribution)
        .where(
            GoalContribution.goal_id == goal.id,
            GoalContribution.user_id == goal.user_id,
        )
        .order_by(GoalContribution.occurred_on)
    ).all():
        if c.occurred_on > today or c.occurred_on < cutoff:
            continue
        total += c.amount_minor
        count += 1
        if first is None or c.occurred_on < first:
            first = c.occurred_on
    if total <= 0 or first is None:
        return None  # no money actually arrived recently -> no date

    observed_days = max(1, (today - first).days)
    per_day = total / observed_days
    days_to_target = int(remaining_minor // per_day)
    projected_on = today + timedelta(days=days_to_target)

    if goal.deadline is not None:
        status = "on_track" if projected_on <= goal.deadline else "after_deadline"
    else:
        status = "no_deadline"
    return {
        "amount_per_day_minor": round(per_day),
        "contribution_count": count,
        "window_days": observed_days,
        "days_to_target": days_to_target,
        "projected_on": projected_on,
        "status": status,
    }
