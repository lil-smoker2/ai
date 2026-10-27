from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow

QUANTITY_EVENT_REASONS = ("open", "purchase", "adjustment", "sale", "loss", "return")


class InventoryCategory(Base):
    __tablename__ = "inventory_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("inventory_categories.id"))
    name: Mapped[str] = mapped_column(String(120))
    quantity_owned: Mapped[int] = mapped_column(Integer, default=0)
    target_quantity: Mapped[int | None] = mapped_column(Integer, default=None)
    unit: Mapped[str | None] = mapped_column(String(30), default=None)
    # Null means price unknown: financial totals must then show "Price needed".
    estimated_unit_cost_minor: Mapped[int | None] = mapped_column(
        BigInteger, default=None
    )
    # True only when the user verified a real price; estimates are never invented.
    price_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    price_source: Mapped[str | None] = mapped_column(String(120), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    image_asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("assets.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Soft delete preserves purchase/quantity history.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class QuantityEvent(Base):
    __tablename__ = "quantity_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    change: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Enum(*QUANTITY_EVENT_REASONS, name="qty_reason"))
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), default=None
    )
    occurred_on: Mapped[date] = mapped_column(Date, default=lambda: date.today())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
