"""Shopping contracts: lists, planned items and confirmed purchase events.

estimated_total = item_cost + delivery + transport + fees (spec 4.4).
A missing unit price yields price_needed=True and a null total - never zero.
"""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Page

PRICE_SOURCES = ("estimate", "verified")


class ListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notes: str | None = None
    goal_id: int | None = None


class ListUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = None
    goal_id: int | None = None


class ListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    notes: str | None
    goal_id: int | None
    created_at: datetime


class ListPage(BaseModel):
    lists: list[ListOut]
    page: Page


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=80)
    subcategory: str | None = Field(default=None, max_length=80)
    quantity_needed: int = Field(default=1, ge=1)
    estimated_unit_cost_minor: int | None = Field(default=None, ge=0)
    price_source: str = Field(default="estimate", pattern=f"^({'|'.join(PRICE_SOURCES)})$")
    seller: str | None = Field(default=None, max_length=120)
    delivery_cost_minor: int = Field(default=0, ge=0)
    transport_cost_minor: int = Field(default=0, ge=0)
    fees_minor: int = Field(default=0, ge=0)
    inventory_item_id: int | None = None
    goal_id: int | None = None
    notes: str | None = None


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=80)
    subcategory: str | None = Field(default=None, max_length=80)
    quantity_needed: int | None = Field(default=None, ge=1)
    estimated_unit_cost_minor: int | None = Field(default=None, ge=0)
    price_source: str | None = Field(default=None, pattern=f"^({'|'.join(PRICE_SOURCES)})$")
    seller: str | None = None
    delivery_cost_minor: int | None = Field(default=None, ge=0)
    transport_cost_minor: int | None = Field(default=None, ge=0)
    fees_minor: int | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, pattern="^(needed|purchased)$")
    inventory_item_id: int | None = None
    goal_id: int | None = None
    notes: str | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    list_id: int
    name: str
    category: str | None = None
    subcategory: str | None = None
    quantity_needed: int
    estimated_unit_cost_minor: int | None
    price_source: str
    seller: str | None
    delivery_cost_minor: int
    transport_cost_minor: int
    fees_minor: int
    status: str
    inventory_item_id: int | None
    goal_id: int | None
    notes: str | None
    created_at: datetime
    # Calculated from saved figures only.
    estimated_item_cost_minor: int | None = None
    estimated_total_minor: int | None = None
    price_needed: bool = False


class PurchaseCreate(BaseModel):
    """Confirmed purchase details. The user states what was actually paid;
    LifeSmart records that event and nothing else."""

    quantity: int = Field(ge=1)
    amount_paid_minor: int = Field(gt=0)
    occurred_on: date | None = None
    account_id: int | None = None
    add_to_inventory: bool = True
    idempotency_key: str = Field(min_length=8, max_length=64)


class PurchaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shopping_item_id: int
    quantity: int
    amount_paid_minor: int
    currency: str
    occurred_on: date
    transaction_id: int | None
    added_inventory_quantity: int
    idempotency_key: str
    created_at: datetime
