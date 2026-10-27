"""Shopping records: lists, planned items and confirmed purchase events.

Prices distinguish user estimates from manually verified figures; an unknown
price is null, never a fabricated zero. Purchases exist only as events the
user confirmed - LifeSmart never claims a purchase it has no record of.
"""
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow

LIST_ITEM_STATUSES = ("needed", "purchased")
# How a line's unit price became known (spec 4.4 distinction).
PRICE_SOURCES = ("estimate", "verified")


class ShoppingList(Base):
    __tablename__ = "shopping_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("goals.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class ShoppingItem(Base):
    __tablename__ = "shopping_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("shopping_lists.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    quantity_needed: Mapped[int] = mapped_column(Integer, default=1)
    # Null unit cost means unknown: totals then show "Price needed".
    estimated_unit_cost_minor: Mapped[int | None] = mapped_column(
        BigInteger, default=None
    )
    price_source: Mapped[str] = mapped_column(
        Enum(*PRICE_SOURCES, name="price_source"), default="estimate"
    )
    seller: Mapped[str | None] = mapped_column(String(120), default=None)
    delivery_cost_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    transport_cost_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    fees_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(
        Enum(*LIST_ITEM_STATUSES, name="shopping_item_status"), default="needed"
    )
    inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id"), default=None
    )
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id"), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PurchaseRecord(Base):
    """One confirmed purchase. Idempotent per (user, key): repeated requests
    return the first record instead of writing duplicate events."""

    __tablename__ = "purchase_records"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shopping_item_id: Mapped[int] = mapped_column(
        ForeignKey("shopping_items.id"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    # Total actually paid for this event (all units), never an estimate here.
    amount_paid_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(8), default="KES")
    occurred_on: Mapped[date] = mapped_column(Date, default=lambda: date.today())
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), default=None
    )
    added_inventory_quantity: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
