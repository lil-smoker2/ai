from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow

ACCOUNT_TYPES = ("cash", "mpesa", "bank", "wallet", "custom")
TRANSACTION_TYPES = ("income", "expense", "transfer")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(Enum(*ACCOUNT_TYPES, name="account_type"))
    # Manually tracked accounts are not institution-verified.
    is_synced: Mapped[bool] = mapped_column(Boolean, default=False)
    # Balance is only meaningful once the user explicitly initialized it.
    initialized: Mapped[bool] = mapped_column(Boolean, default=False)
    initial_balance_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(Enum(*TRANSACTION_TYPES, name="transaction_type"))
    # Always a positive integer in minor units (cents). Direction comes from type.
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(8), default="KES")
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str | None] = mapped_column(String(80), default=None)
    description: Mapped[str | None] = mapped_column(String(255), default=None)
    # income -> to_account_id; expense -> from_account_id; transfer -> both.
    from_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), default=None
    )
    to_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), default=None, index=True
    )
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id"), default=None)
    reference: Mapped[str | None] = mapped_column(String(120), default=None)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), default=None)
    # Audit-friendly reversal: original stays, a compensating record is created.
    reversed: Mapped[bool] = mapped_column(Boolean, default=False)
    reversal_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
