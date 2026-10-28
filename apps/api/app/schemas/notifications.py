"""Notification contracts: the preference switches, and the alerts derived
from them.

The alert shapes carry money only as integer minor units. Any sentence the
frontend builds from one has to do the formatting itself, so a figure can never
be shown in one currency by the API and another by the page.
"""
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict

AlertKind = Literal["deadline", "task", "fee", "stock", "savings"]
Severity = Literal["overdue", "due", "soon", "attention"]


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


class AlertOut(BaseModel):
    """One thing worth looking at, and the record it came from."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    kind: AlertKind
    severity: Severity
    title: str
    detail: str | None
    # What is still owed, short or outstanding. Null means the alert has no
    # money in it, or the figure was never recorded - not that it is zero.
    amount_minor: int | None
    # When set, the amount a period of saving would need to reach the target.
    period_amount_minor: int | None
    period_label: str | None
    due_on: date | None
    days_out: int | None
    link: str


class AlertsOut(BaseModel):
    generated_on: date
    generated_at: time
    # Which currency every *_minor figure on this page is in, taken from the
    # profile rather than assumed.
    currency: str
    alerts: list[AlertOut]
    count: int
    # Kinds switched off, so an empty list can say "your switches hid these"
    # rather than "nothing needs you".
    hidden_by_preferences: list[AlertKind]
    in_quiet_hours: bool
    quiet_ends_at: time | None
    quiet_start: time | None
    quiet_end: time | None
