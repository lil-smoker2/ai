"""Savings & Earnings records: recurring income sources, business entries and
the places money can sit.

Business rows are the user's actual confirmed figures. Income sources are
*expected* values used only for planning forecasts - they are never treated
as received money or as a bank balance. Savings vehicles carry what the person
was quoted, and are never a balance.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow

INCOME_FREQUENCIES = ("daily", "weekly", "monthly", "yearly", "once")
INCOME_RELIABILITY = ("uncertain", "likely", "confirmed")
BUSINESS_RECORD_TYPES = ("revenue", "expense")
# The ways money can be kept or put to work, as the person names them.
VEHICLE_KINDS = (
    "mpesa",
    "bank",
    "sacco",
    "money_market",
    "shares",
    "betting",
    "other",
)
# Which way money moved, seen from the place that holds it, not from the
# person: "in" went into the vehicle (saved, used to buy, staked), "out" came
# back to them (a withdrawal, a cash-out, a winning paid out).
VEHICLE_FLOW_DIRECTIONS = ("in", "out")


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


class SavingsVehicle(Base):
    """A place money can sit: an M-PESA savings product, a bank or SACCO
    account, a share holding, a betting site.

    The rate and the valuation are what the person was told or last checked,
    kept with the date they checked it, because this app has no network
    connection and cannot know any platform's current rate. Nothing here is
    verified, and a vehicle is not a balance: the money itself belongs to an
    account on the Money page, so a rate written here makes no claim about what
    anyone actually holds.

    A betting site gets a name and a link, never a rate: no return can be
    projected from a gamble, and a field that invites one would be a lie.
    """

    __tablename__ = "savings_vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(Enum(*VEHICLE_KINDS, name="vehicle_kind"))
    url: Mapped[str | None] = mapped_column(String(300), default=None)
    # Percent per year, exactly as quoted (10.75 means 10.75% a year).
    rate_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), default=None
    )
    rate_checked_on: Mapped[date | None] = mapped_column(Date, default=None)
    # For a holding: how many units, and what the person last valued them at.
    # A value nobody entered stays null - it is never read as free or as zero.
    units: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), default=None)
    value_minor: Mapped[int | None] = mapped_column(BigInteger, default=None)
    valued_on: Mapped[date | None] = mapped_column(Date, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VehicleFlow(Base):
    """Money the person says went into or came back out of a vehicle.

    These rows are notes, not ledger entries: they deliberately do not move any
    account balance, because recording the same transfer here and on the Money
    page would count the same money twice. For a betting site they are the only
    honest figures there are - what was staked, what came back, and the
    difference between them.
    """

    __tablename__ = "vehicle_flows"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Children carry the owner too, so every query can be scoped by user_id the
    # same way as every other owned table (export and reset depend on it).
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("savings_vehicles.id"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    direction: Mapped[str] = mapped_column(
        Enum(*VEHICLE_FLOW_DIRECTIONS, name="vehicle_flow_direction")
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
