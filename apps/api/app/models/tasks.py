"""Tasks & Reminders: plans turned into manageable actions.

Completing a task only records that the user did the action - it never
mutates money or fee state on its own (spec 4.9: a reminder to pay fees being
marked done is not proof the fees were paid). Unknown/absent due dates are
just null, never a fabricated deadline.
"""
from datetime import date, datetime, time

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow

TASK_STATUSES = ("proposed", "pending", "in_progress", "completed", "cancelled")
TASK_PRIORITIES = ("low", "medium", "high", "critical")
TASK_RECURRENCE = ("none", "daily", "weekly", "monthly", "yearly")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    due_on: Mapped[date | None] = mapped_column(Date, default=None)
    due_time: Mapped[time | None] = mapped_column(Time, default=None)
    priority: Mapped[str] = mapped_column(
        Enum(*TASK_PRIORITIES, name="task_priority"), default="medium"
    )
    status: Mapped[str] = mapped_column(
        Enum(*TASK_STATUSES, name="task_status"), default="pending"
    )
    # Optional link to a goal; a task can "come from" a plan without being
    # the proof of the underlying outcome.
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id"), default=None)
    recurrence: Mapped[str] = mapped_column(
        Enum(*TASK_RECURRENCE, name="task_recurrence"), default="none"
    )
    # Days before the due date to nudge; null = no reminder scheduled.
    remind_before_days: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
