"""Saved net worth: one valuation snapshot per user per day.

The figure is always *derived* from inventory records - the user never types
it. Rows exist so the number is a saved record that history can be read from,
not a value recomputed only while a page is open. An unknown total stays null
rather than being faked as zero, exactly like every other money figure here.
"""
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow


class NetWorthSnapshot(Base):
    __tablename__ = "net_worth_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "on_date", name="uq_net_worth_user_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # One row per calendar day; the day's edits collapse into its final value.
    on_date: Mapped[date] = mapped_column(Date, default=lambda: date.today())
    # Full value of what is owned. Null when some owned items are unpriced,
    # because a total with holes in it is not a net worth.
    net_worth_minor: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # Sum over the priced items only, so the UI can still say "at least this".
    priced_value_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    valued_items: Mapped[int] = mapped_column(Integer, default=0)
    unpriced_items: Mapped[int] = mapped_column(Integer, default=0)
    # True when nothing was left out for want of a price.
    complete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )
