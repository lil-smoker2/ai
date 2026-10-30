"""Student Life records: school fee obligations, accommodation options and a
food budget.

Everything here is user-entered or evidence-backed. A fee only counts as paid
through a recorded payment (optionally linked to a transaction); a hostel is
never marked booked/available without the user updating its checked status -
an unverified option stays 'unchecked' (spec 4.10: never claim a fee paid or a
hostel booked without verified evidence).
"""
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Float,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow

FEE_CATEGORIES = ("tuition", "registration", "other")
# A hostel's availability as last seen by the user; unknown until checked.
HOSTEL_STATUSES = ("unchecked", "available", "taken", "booked")


class FeeObligation(Base):
    __tablename__ = "fee_obligations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(
        Enum(*FEE_CATEGORIES, name="fee_category"), default="tuition"
    )
    amount_due_minor: Mapped[int] = mapped_column(BigInteger)
    # Sum of recorded payments; kept in sync so outstanding is exact.
    amount_paid_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    due_on: Mapped[date | None] = mapped_column(Date, default=None)
    # Payment evidence/reference the user can cite (never auto-filled).
    reference: Mapped[str | None] = mapped_column(String(120), default=None)
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id"), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class FeePayment(Base):
    """One confirmed fee payment. Idempotent per (user, key)."""

    __tablename__ = "fee_payments"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fee_id: Mapped[int] = mapped_column(ForeignKey("fee_obligations.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(8), default="KES")
    occurred_on: Mapped[date] = mapped_column(Date, default=lambda: date.today())
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), default=None
    )
    reference: Mapped[str | None] = mapped_column(String(120), default=None)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class HostelOption(Base):
    __tablename__ = "hostel_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(160), default=None)
    # Null price means unknown, never a fabricated zero.
    monthly_rent_minor: Mapped[int | None] = mapped_column(BigInteger, default=None)
    deposit_minor: Mapped[int | None] = mapped_column(BigInteger, default=None)
    status: Mapped[str] = mapped_column(
        Enum(*HOSTEL_STATUSES, name="hostel_status"), default="unchecked"
    )
    facilities: Mapped[str | None] = mapped_column(Text, default=None)
    booking_source: Mapped[str | None] = mapped_column(String(160), default=None)
    # When the user last verified availability; null until they check.
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class FoodBudget(Base):
    """A single per-user food budget. Amounts are planning estimates; a null
    budget simply means "not set yet", never zero."""

    __tablename__ = "food_budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    weekly_budget_minor: Mapped[int | None] = mapped_column(BigInteger, default=None)
    monthly_budget_minor: Mapped[int | None] = mapped_column(BigInteger, default=None)
    period: Mapped[str] = mapped_column(String(20), default="weekly")  # weekly or monthly
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)




class FoodStock(Base):
    """Track food items purchased with quantity and consumption rate."""
    __tablename__ = "food_stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    quantity_bought: Mapped[float] = mapped_column(Float, default=0)
    unit: Mapped[str] = mapped_column(String(20), default="kg")
    quantity_per_day: Mapped[float] = mapped_column(Float, default=0)
    purchase_date: Mapped[date] = mapped_column(Date, default=date.today)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
