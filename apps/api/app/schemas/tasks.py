"""Tasks & Reminders contracts."""
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field

TASK_STATUSES = ("proposed", "pending", "in_progress", "completed", "cancelled")
TASK_PRIORITIES = ("low", "medium", "high", "critical")
TASK_RECURRENCE = ("none", "daily", "weekly", "monthly", "yearly")

_STATUS_RE = f"^({'|'.join(TASK_STATUSES)})$"
_PRIORITY_RE = f"^({'|'.join(TASK_PRIORITIES)})$"
_RECURRENCE_RE = f"^({'|'.join(TASK_RECURRENCE)})$"


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = None
    due_on: date | None = None
    due_time: time | None = None
    priority: str = Field(default="medium", pattern=_PRIORITY_RE)
    status: str = Field(default="pending", pattern=_STATUS_RE)
    goal_id: int | None = None
    recurrence: str = Field(default="none", pattern=_RECURRENCE_RE)
    remind_before_days: int | None = Field(default=None, ge=0, le=90)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    due_on: date | None = None
    due_time: time | None = None
    priority: str | None = Field(default=None, pattern=_PRIORITY_RE)
    status: str | None = Field(default=None, pattern=_STATUS_RE)
    goal_id: int | None = None
    recurrence: str | None = Field(default=None, pattern=_RECURRENCE_RE)
    remind_before_days: int | None = Field(default=None, ge=0, le=90)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    due_on: date | None
    due_time: time | None
    priority: str
    status: str
    goal_id: int | None
    recurrence: str
    remind_before_days: int | None
    created_at: datetime
    completed_at: datetime | None
    # Computed: past-due and not finished. Never implies anything about money.
    is_overdue: bool = False


class SnoozeRequest(BaseModel):
    days: int = Field(ge=1, le=365)
