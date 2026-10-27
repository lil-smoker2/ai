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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow

GOAL_TYPES = ("money", "quantity", "obligation", "custom")
GOAL_STATUSES = ("active", "paused", "completed")
GOAL_PRIORITIES = ("low", "medium", "high", "critical")


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(Enum(*GOAL_TYPES, name="goal_type"))
    status: Mapped[str] = mapped_column(
        Enum(*GOAL_STATUSES, name="goal_status"), default="active"
    )
    target_amount_minor: Mapped[int | None] = mapped_column(BigInteger, default=None)
    target_quantity: Mapped[int | None] = mapped_column(Integer, default=None)
    current_quantity: Mapped[int | None] = mapped_column(Integer, default=None)
    estimated_unit_cost_minor: Mapped[int | None] = mapped_column(
        BigInteger, default=None
    )
    deadline: Mapped[date | None] = mapped_column(Date, default=None)
    priority: Mapped[str] = mapped_column(
        Enum(*GOAL_PRIORITIES, name="goal_priority"), default="medium"
    )
    inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id"), default=None
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class GoalContribution(Base):
    __tablename__ = "goal_contributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    occurred_on: Mapped[date] = mapped_column(Date, default=lambda: date.today())
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), default=None
    )
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), default=None
    )
    note: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
