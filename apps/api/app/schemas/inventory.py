from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import Page


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ItemBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category_id: int
    quantity_owned: int = Field(default=0, ge=0)
    target_quantity: int | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=30)
    # Money in integer minor units. Null means unknown price, never fake zero.
    estimated_unit_cost_minor: int | None = Field(default=None, ge=0)
    price_verified: bool = False
    price_source: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    image_asset_id: str | None = None


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category_id: int | None = None
    target_quantity: int | None = Field(default=None, ge=0)
    unit: str | None = None
    estimated_unit_cost_minor: int | None = Field(default=None, ge=0)
    price_verified: bool | None = None
    price_source: str | None = None
    notes: str | None = None
    image_asset_id: str | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category_id: int
    category_name: str | None = None
    quantity_owned: int
    target_quantity: int | None
    unit: str | None
    estimated_unit_cost_minor: int | None
    price_verified: bool
    price_source: str | None
    notes: str | None
    image_asset_id: str | None
    created_at: datetime
    # Calculated fields, derived from saved records only.
    shortage: int = 0
    # Null when price unknown or shortage is zero -> UI shows "Price needed".
    estimated_cost_to_target_minor: int | None = None
    price_needed: bool = False


class ItemPage(BaseModel):
    items: list[ItemOut]
    page: Page


class QuantityAdjust(BaseModel):
    change: int
    reason: str = Field(default="adjustment", pattern="^(open|purchase|adjustment|sale|loss|return)$")
    occurred_on: date | None = None

    @field_validator("change")
    @classmethod
    def change_not_zero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("change must not be zero")
        return v


class QuantityEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    change: int
    reason: str
    transaction_id: int | None
    occurred_on: date
