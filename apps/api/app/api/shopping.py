"""Shopping API: lists, planned items and the transactional purchase workflow.

Recording a purchase (spec 4.4) confirms quantity/amount/date/funding account,
writes the expense transaction, updates inventory and goal progress and marks
the line purchased - all in one commit, idempotent per (user, idempotency key)
so repeated requests never duplicate the purchase.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned
from app.core.database import get_db
from app.models.finance import Account, Transaction
from app.models.goal import Goal
from app.models.inventory import InventoryItem, QuantityEvent
from app.models.shopping import PurchaseRecord, ShoppingItem, ShoppingList
from app.models.user import User
from app.schemas.common import Page
from app.schemas.shopping import (
    ItemCreate,
    ItemOut,
    ItemUpdate,
    ListCreate,
    ListOut,
    ListPage,
    ListUpdate,
    PurchaseCreate,
    PurchaseOut,
)

router = APIRouter(prefix="/api/shopping", tags=["shopping"])


def inv_item_id_goal(db: Session, inv_item: InventoryItem) -> int | None:
    """Goal (if any) bound to this inventory item, for quantity progress."""
    return db.scalar(
        select(Goal.id).where(Goal.inventory_item_id == inv_item.id)
    )


def _item_out(item: ShoppingItem) -> ItemOut:
    out = ItemOut.model_validate(item)
    if item.estimated_unit_cost_minor is None:
        out.price_needed = True  # no financial total from a missing price
    else:
        out.estimated_item_cost_minor = item.quantity_needed * item.estimated_unit_cost_minor
        out.estimated_total_minor = (
            out.estimated_item_cost_minor
            + item.delivery_cost_minor
            + item.transport_cost_minor
            + item.fees_minor
        )
    return out


def _get_list(db: Session, list_id: int, user_id: int) -> ShoppingList:
    lst = get_owned(db, ShoppingList, list_id, user_id)
    if lst.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    return lst


def _get_item(db: Session, item_id: int, user_id: int) -> ShoppingItem:
    item = get_owned(db, ShoppingItem, item_id, user_id)
    _get_list(db, item.list_id, user_id)
    return item


def _validate_links(db: Session, user: User, goal_id: int | None,
                    inventory_item_id: int | None) -> None:
    if goal_id is not None:
        get_owned(db, Goal, goal_id, user.id)
    if inventory_item_id is not None:
        get_owned(db, InventoryItem, inventory_item_id, user.id)


@router.get("/lists", response_model=ListPage)
def list_lists(page: int = Query(default=1, ge=1),
               page_size: int = Query(default=50, ge=1, le=200),
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    query = select(ShoppingList).where(
        ShoppingList.user_id == user.id, ShoppingList.deleted_at.is_(None)
    )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(ShoppingList.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return ListPage(
        lists=rows, page=Page(total=total, page=page, page_size=page_size)
    )


@router.post("/lists", response_model=ListOut, status_code=201)
def create_list(body: ListCreate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    _validate_links(db, user, body.goal_id, None)
    lst = ShoppingList(user_id=user.id, **body.model_dump())
    db.add(lst)
    db.commit()
    return lst


@router.get("/lists/{list_id}", response_model=ListOut)
def get_list(list_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    return _get_list(db, list_id, user.id)


@router.put("/lists/{list_id}", response_model=ListOut)
def update_list(list_id: int, body: ListUpdate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    lst = _get_list(db, list_id, user.id)
    data = body.model_dump(exclude_unset=True)
    _validate_links(db, user, data.get("goal_id"), None)
    for field, value in data.items():
        setattr(lst, field, value)
    db.commit()
    return lst


@router.post("/lists/{list_id}/generate-from-shortages", response_model=list[ItemOut])
def generate_from_shortages(list_id: int, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)):
    """Add one line per inventory item below target. Shortage and any known
    unit price come from saved inventory records only - nothing is invented."""
    lst = _get_list(db, list_id, user.id)
    items = db.scalars(
        select(InventoryItem).where(
            InventoryItem.user_id == user.id,
            InventoryItem.deleted_at.is_(None),
            InventoryItem.target_quantity.is_not(None),
        )
    ).all()
    existing_names = {
        i.name.lower()
        for i in db.scalars(
            select(ShoppingItem).where(
                ShoppingItem.list_id == lst.id,
                ShoppingItem.user_id == user.id,
            )
        ).all()
    }
    created: list[ShoppingItem] = []
    for item in items:
        shortage = max(item.target_quantity - item.quantity_owned, 0)
        if shortage <= 0 or item.name.lower() in existing_names:
            continue
        line = ShoppingItem(
            list_id=lst.id,
            user_id=user.id,
            name=item.name,
            quantity_needed=shortage,
            estimated_unit_cost_minor=item.estimated_unit_cost_minor,
            # A price is only "verified" when the inventory record says so.
            price_source="verified" if item.price_verified else "estimate",
            inventory_item_id=item.id,
        )
        db.add(line)
        created.append(line)
    db.commit()
    return [_item_out(i) for i in created]


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(list_id: int, confirm: bool = Query(default=False),
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """Soft delete. Purchase history on the list's lines is preserved."""
    if not confirm:
        raise HTTPException(status_code=400, detail="Deletion requires confirm=true")
    lst = _get_list(db, list_id, user.id)
    lst.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return None


@router.get("/lists/{list_id}/items", response_model=list[ItemOut])
def list_items(list_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    lst = _get_list(db, list_id, user.id)
    items = db.scalars(
        select(ShoppingItem)
        .where(ShoppingItem.list_id == lst.id, ShoppingItem.user_id == user.id)
        .order_by(ShoppingItem.created_at)
    ).all()
    return [_item_out(i) for i in items]


@router.post("/lists/{list_id}/items", response_model=ItemOut, status_code=201)
def create_item(list_id: int, body: ItemCreate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    lst = _get_list(db, list_id, user.id)
    _validate_links(db, user, body.goal_id, body.inventory_item_id)
    item = ShoppingItem(list_id=lst.id, user_id=user.id, **body.model_dump())
    db.add(item)
    db.commit()
    return _item_out(item)


@router.get("/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    return _item_out(_get_item(db, item_id, user.id))


@router.put("/items/{item_id}", response_model=ItemOut)
def update_item(item_id: int, body: ItemUpdate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    item = _get_item(db, item_id, user.id)
    if item.status == "purchased":
        raise HTTPException(
            status_code=409,
            detail="Purchased lines are kept; record corrections via transactions",
        )
    data = body.model_dump(exclude_unset=True)
    _validate_links(db, user, data.get("goal_id"), data.get("inventory_item_id"))
    for field, value in data.items():
        setattr(item, field, value)
    db.commit()
    return _item_out(item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """Remove a planned line. Recorded purchases stay in the audit trail."""
    item = _get_item(db, item_id, user.id)
    db.delete(item)
    db.commit()
    return None


@router.get("/items/{item_id}/purchases", response_model=list[PurchaseOut])
def item_purchases(item_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    item = _get_item(db, item_id, user.id)
    return db.scalars(
        select(PurchaseRecord)
        .where(PurchaseRecord.shopping_item_id == item.id)
        .order_by(PurchaseRecord.occurred_on.desc(), PurchaseRecord.id.desc())
    ).all()


@router.get("/purchases", response_model=list[PurchaseOut])
def recent_purchases(limit: int = Query(default=20, ge=1, le=100),
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    return db.scalars(
        select(PurchaseRecord)
        .where(PurchaseRecord.user_id == user.id)
        .order_by(PurchaseRecord.created_at.desc(), PurchaseRecord.id.desc())
        .limit(limit)
    ).all()


@router.post("/items/{item_id}/purchase", response_model=PurchaseOut, status_code=201)
def record_purchase(item_id: int, body: PurchaseCreate,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Transactional, idempotent purchase workflow (spec 4.4)."""
    # Idempotent replay: return the original record, write nothing.
    existing = db.scalars(
        select(PurchaseRecord).where(
            PurchaseRecord.user_id == user.id,
            PurchaseRecord.idempotency_key == body.idempotency_key,
        )
    ).first()
    if existing:
        db.rollback()
        return existing

    item = _get_item(db, item_id, user.id)
    if item.status == "purchased":
        raise HTTPException(
            status_code=409,
            detail="Line already purchased; use a new idempotency key to record "
                   "another purchase against it",
        )
    account = None
    if body.account_id is not None:
        account = get_owned(db, Account, body.account_id, user.id)

    txn = Transaction(
        user_id=user.id,
        type="expense",
        amount_minor=body.amount_paid_minor,
        currency=user.currency,
        occurred_on=body.occurred_on or item.created_at.date(),
        category="shopping",
        description=f"Purchase: {item.name}",
        from_account_id=account.id if account else None,
        idempotency_key=f"purchase:{body.idempotency_key}",
    )
    db.add(txn)
    db.flush()  # txn.id needed by the linked records below

    added_qty = 0
    if body.add_to_inventory and item.inventory_item_id is not None:
        inv_item = get_owned(db, InventoryItem, item.inventory_item_id, user.id)
        inv_item.quantity_owned += body.quantity
        added_qty = body.quantity
        db.add(QuantityEvent(
            item_id=inv_item.id, user_id=user.id, change=body.quantity,
            reason="purchase", transaction_id=txn.id,
            occurred_on=txn.occurred_on,
        ))
        # Linked quantity goals track the same owned quantity. Each distinct
        # goal is updated exactly once, even if reached via item and line.
        goal_ids = {item.goal_id, inv_item_id_goal(db, inv_item)} - {None}
        for goal_id in goal_ids:
            goal = db.get(Goal, goal_id)
            if goal is not None and goal.type == "quantity" and goal.status != "completed":
                goal.current_quantity = (goal.current_quantity or 0) + body.quantity

    record = PurchaseRecord(
        shopping_item_id=item.id,
        user_id=user.id,
        quantity=body.quantity,
        amount_paid_minor=body.amount_paid_minor,
        currency=user.currency,
        occurred_on=txn.occurred_on,
        transaction_id=txn.id,
        added_inventory_quantity=added_qty,
        idempotency_key=body.idempotency_key,
    )
    db.add(record)
    item.status = "purchased"
    try:
        db.commit()
    except IntegrityError:
        # Concurrent replay on the (user, key) unique constraint.
        db.rollback()
        existing = db.scalars(
            select(PurchaseRecord).where(
                PurchaseRecord.user_id == user.id,
                PurchaseRecord.idempotency_key == body.idempotency_key,
            )
        ).first()
        if existing:
            return existing
        raise
    return record
