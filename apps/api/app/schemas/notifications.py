"""Notification preference contracts."""
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict


class NotificationPreferenceUpdate(BaseModel):
    deadline_alerts: bool | None = None
    task_reminders: bool | None = None
    low_stock_warnings: bool | None = None
    savings_nudges: bool | None = None
    fee_due_alerts: bool | None = None
    quiet_start: time | None = None
    quiet_end: time | None = None


class NotificationPreferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deadline_alerts: bool
    task_reminders: bool
    low_stock_warnings: bool
    savings_nudges: bool
    fee_due_alerts: bool
    quiet_start: time | None
    quiet_end: time | None
    updated_at: datetime
