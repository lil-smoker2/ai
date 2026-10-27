"""Notification preferences: one row per user controlling which nudges the
app surfaces. Local-first app, so these gate in-app alerts only; enabling a
channel here never implies an external delivery mechanism exists."""
from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, index=True
    )
    deadline_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    task_reminders: Mapped[bool] = mapped_column(Boolean, default=True)
    low_stock_warnings: Mapped[bool] = mapped_column(Boolean, default=True)
    savings_nudges: Mapped[bool] = mapped_column(Boolean, default=True)
    fee_due_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    # Optional quiet hours (null = no quiet window).
    quiet_start: Mapped[time | None] = mapped_column(Time, default=None)
    quiet_end: Mapped[time | None] = mapped_column(Time, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
