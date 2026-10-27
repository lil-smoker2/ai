"""Savings & Earnings records: recurring income sources and business entries.

Business rows are the user's actual confirmed figures. Income sources are
*expected* values used only for planning forecasts - they are never treated
as received money or as a bank balance.
"""
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow

INCOME_FREQUENCIES = ("daily", "weekly", "monthly", "yearly", "once")
INCOME_RELIABILITY = ("uncertain", "likely", "confirmed")
BUSINESS_RECORD_TYPES = ("revenue", "expense")


class IncomeSource(Base):
    __tablename__ = "income_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    # Expected amount per occurrence, in integer minor units. Never "received".
    expected_amount_minor: Mapped[int] = mapped_column(BigInteger)
    frequency: Mapped[str] = mapped_column(
        Enum(*INCOME_FREQUENCIES, name="income_frequency"), default="monthly"
    )
    next_expected_date: Mapped[date | None] = mapped_column(Date, default=None)
    reliability: Mapped[str] = mapped_column(
        Enum(*INCOME_RELIABILITY, name="income_reliability"), default="likely"
    )
    # Inactive sources are excluded from the planning forecast.
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BusinessRecord(Base):
    """A single confirmed business entry: revenue or an expense."""

    __tablename__ = "business_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    business_name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(
        Enum(*BUSINESS_RECORD_TYPES, name="business_record_type")
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    # Optional finer label, e.g. direct_cost or operating_expense for expenses.
    category: Mapped[str | None] = mapped_column(String(80), default=None)
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), default=None
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
