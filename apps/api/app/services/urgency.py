"""How pressing an open task is, from its priority and how late it has run.

The score is a small, fixed arithmetic - nothing learned or guessed - so the
same task always reads the same way and the two numbers behind it can be shown
alongside it. It lives beside the task, not stored on it: completing or
rescheduling changes the score the same way they change the row.

The arithmetic, in priority points plus overdue points:

* priority points: low 0, medium 5, high 10, critical 20 - the user's own label,
  just given a magnitude so two tasks can be compared.
* overdue points: three per day past the due date, counted to a ceiling of ten
  days (so at most 30). A task not yet late adds nothing; being late does not
  lower the priority it already carries, it piles on top of it.

An open task with no due date is "unscheduled" and scores on priority alone -
the record has no date to be late against, so no lateness is invented. A
finished or cancelled task is "settled" and scores zero: it asks for no action,
and a done task outranking an undone one would be noise.
"""
from __future__ import annotations

from datetime import date

PRIORITY_POINTS = {"low": 0, "medium": 5, "high": 10, "critical": 20}

# Points added per day past the due date, and the ceiling on that lateness so a
# long-abandoned task cannot swamp everything else.
OVERDAY_POINTS = 3
MAX_COUNTED_DAYS_OVERDUE = 10

# A task due within this many days (but not yet late) reads as "due soon".
DUE_SOON_WINDOW_DAYS = 3

_OPEN_STATUSES = {"proposed", "pending", "in_progress"}


def score(priority: str, due_on: date | None, status: str,
          today: date | None = None) -> dict:
    """The urgency of one task as {score, band, priority_points, overdue_points}."""
    today = today or date.today()
    if status not in _OPEN_STATUSES:
        return {"score": 0, "band": "settled", "priority_points": 0,
                "overdue_points": 0}

    priority_points = PRIORITY_POINTS.get(priority, 0)
    if due_on is None:
        return {"score": priority_points, "band": "unscheduled",
                "priority_points": priority_points, "overdue_points": 0}

    days_overdue = (today - due_on).days
    if days_overdue > 0:
        overdue_points = min(days_overdue, MAX_COUNTED_DAYS_OVERDUE) * OVERDAY_POINTS
        band = "overdue"
    elif (due_on - today).days <= DUE_SOON_WINDOW_DAYS:
        overdue_points = 0
        band = "due-soon"
    else:
        overdue_points = 0
        band = "scheduled"

    return {"score": priority_points + overdue_points, "band": band,
            "priority_points": priority_points, "overdue_points": overdue_points}
