"""Inventory API: categories, items with shortage calculations, quantity events.

Any change to an item also re-saves the derived net worth, so the recorded
figure follows the inventory instead of being maintained separately.
"""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned
from app.core.database import get_db
from app.models.inventory import InventoryCategory, InventoryItem, QuantityEvent
from app.models.user import User
from app.schemas.common import Page
from app.schemas.inventory import (
    CategoryCreate,
    CategoryOut,
    InventoryForecastsOut,
    ItemCreate,
    ItemOut,
    ItemPage,
    ItemUpdate,
    QuantityAdjust,
    QuantityEventOut,
)
from app.services import forecasting as forecasting_service
from app.services import valuation as valuation_service

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


def _item_out(db: Session, item: InventoryItem) -> ItemOut:
    shortage = max((item.target_quantity - item.quantity_owned), 0) if (
        item.target_quantity is not None
    ) else 0
    cost = None
    price_needed = False
    if shortage > 0:
        if item.estimated_unit_cost_minor is not None:
            cost = shortage * item.estimated_unit_cost_minor
        else:
            price_needed = True
    elif item.target_quantity is not None:
        # Target already met: nothing left to buy.
        cost = 0
    category = db.get(InventoryCategory, item.category_id)
    return ItemOut(
        id=item.id,
        name=item.name,
        category_id=item.category_id,
        category_name=category.name if category else None,
        quantity_owned=item.quantity_owned,
        target_quantity=item.target_quantity,
        unit=item.unit,
        estimated_unit_cost_minor=item.estimated_unit_cost_minor,
        price_verified=item.price_verified,
        price_source=item.price_source,
        notes=item.notes,
        image_asset_id=item.image_asset_id,
        created_at=item.created_at,
        shortage=shortage,
        estimated_cost_to_target_minor=cost,
        price_needed=price_needed,
    )


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(
        select(InventoryCategory)
        .where(InventoryCategory.user_id == user.id)
        .order_by(InventoryCategory.name)
    ).all()


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryCreate, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    existing = db.scalars(
        select(InventoryCategory).where(
            InventoryCategory.user_id == user.id,
            func.lower(InventoryCategory.name) == body.name.lower(),
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Category already exists")
    category = InventoryCategory(user_id=user.id, name=body.name.strip())
    db.add(category)
    db.commit()
    return category


@router.get("/forecasts", response_model=InventoryForecastsOut)
def replenishment_forecasts(db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)):
    """Projected run-out dates for items with an observed consumption rate.

    Not cached, deliberately: it is read from the same quantity events the rest
    of the app writes, so adjusting a quantity changes the answer immediately."""
    return forecasting_service.forecast_replenishment(db, user)


@router.get("/items", response_model=ItemPage)
def list_items(
    category_id: int | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
    below_target: bool = Query(default=False),
    sort: str = Query(default="name", pattern="^(name|created_at|quantity_owned)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(InventoryItem).where(
        InventoryItem.user_id == user.id, InventoryItem.deleted_at.is_(None)
    )
    if category_id is not None:
        get_owned(db, InventoryCategory, category_id, user.id)
        query = query.where(InventoryItem.category_id == category_id)
    if search:
        query = query.where(func.lower(InventoryItem.name).contains(search.lower()))

    items = db.scalars(query).all()
    # Filtering on a calculated field happens after fetch; inventories are
    # bounded per user and this keeps shortage logic in exactly one place.
    if below_target:
        items = [i for i in items if i.target_quantity is not None
                 and i.quantity_owned < i.target_quantity]

    items.sort(key=lambda i: (getattr(i, sort) or 0) if sort != "name"
               else i.name.lower())
    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]
    return ItemPage(
        items=[_item_out(db, i) for i in page_items],
        page=Page(total=total, page=page, page_size=page_size),
    )


@router.post("/items", response_model=ItemOut, status_code=201)
def create_item(body: ItemCreate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    get_owned(db, InventoryCategory, body.category_id, user.id)
    item = InventoryItem(user_id=user.id, **body.model_dump())
    db.add(item)
    db.flush()
    if item.quantity_owned > 0:
        db.add(QuantityEvent(
            item_id=item.id, user_id=user.id,
            change=item.quantity_owned, reason="open",
            occurred_on=date.today(),
        ))
    valuation_service.record(db, user)
    db.commit()
    return _item_out(db, item)


@router.get("/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    item = get_owned(db, InventoryItem, item_id, user.id)
    if item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    return _item_out(db, item)


@router.put("/items/{item_id}", response_model=ItemOut)
def update_item(item_id: int, body: ItemUpdate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    item = get_owned(db, InventoryItem, item_id, user.id)
    if item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("category_id") is not None:
        get_owned(db, InventoryCategory, data["category_id"], user.id)
    for field, value in data.items():
        setattr(item, field, value)
    valuation_service.record(db, user)
    db.commit()
    return _item_out(db, item)


@router.post("/items/{item_id}/adjust-quantity", response_model=ItemOut)
def adjust_quantity(item_id: int, body: QuantityAdjust, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    item = get_owned(db, InventoryItem, item_id, user.id)
    if item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    new_qty = item.quantity_owned + body.change
    if new_qty < 0:
        raise HTTPException(
            status_code=422,
            detail=f"quantity cannot go below zero (currently {item.quantity_owned})",
        )
    item.quantity_owned = new_qty
    db.add(QuantityEvent(
        item_id=item.id, user_id=user.id, change=body.change,
        reason=body.reason, occurred_on=body.occurred_on or date.today(),
    ))
    valuation_service.record(db, user)
    db.commit()
    return _item_out(db, item)


@router.get("/items/{item_id}/history", response_model=list[QuantityEventOut])
def item_history(item_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    item = get_owned(db, InventoryItem, item_id, user.id)
    return db.scalars(
        select(QuantityEvent)
        .where(QuantityEvent.item_id == item.id, QuantityEvent.user_id == user.id)
        .order_by(QuantityEvent.created_at.desc())
    ).all()


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, confirm: bool = Query(default=False),
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """Soft delete. History is preserved; deletion requires explicit confirm."""
    if not confirm:
        raise HTTPException(status_code=400, detail="Deletion requires confirm=true")
    item = get_owned(db, InventoryItem, item_id, user.id)
    if item.deleted_at is not None:
        return None
    item.deleted_at = datetime.now(timezone.utc)
    valuation_service.record(db, user)
    db.commit()
    return None
