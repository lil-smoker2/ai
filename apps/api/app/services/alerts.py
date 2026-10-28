"""What needs attention today, derived from the records already saved.

Nothing here is stored. There is deliberately no notifications table: a row
written when an alert fires is a claim about the past, and this app's data
changes underneath it - a task completed, a fee paid, a quantity corrected. So
every alert is recomputed from the user's own rows on each request, and one that
stops being true disappears on the next call.

Four rules hold throughout:

* A figure that was never entered produces no alert. A fee with no due date, a
  goal with no target, an item with no quantity target and a task with no date
  are all silent, because "unknown" is not "zero" and is certainly not overdue.
* Each alert is governed by exactly one preference switch, and the two money
  rules on a goal do not overlap: a goal's deadline alerts once it is inside 14
  days or past due, while its savings pace nudges only while more than 14 days
  remain. One goal cannot produce two entries about the same problem.
* Money leaves here as integer minor units in fields, never inside a sentence.
  A figure in prose would either print raw minor units at the user or bake a
  currency name into the backend, and the app has one honest reason to exist:
  that the number it shows is the number it holds.
* Nothing is marked read or dismissed, because nothing is queued. This is a
  view of the present, not an inbox.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.goal import Goal, GoalContribution
from app.models.inventory import InventoryCategory, InventoryItem
from app.models.notifications import NotificationPreference
from app.models.student import FeeObligation
from app.models.tasks import Task
from app.models.user import User

# Which preference switch governs each alert. One kind, one switch.
AlertKind = Literal["deadline", "task", "fee", "stock", "savings"]
Severity = Literal["overdue", "due", "soon", "attention"]

# How far ahead a dated thing counts as approaching. Beyond this the app stays
# quiet, so the list is about now rather than about the whole year.
DUE_WINDOW_DAYS = 14

# The length of the window a savings pace is measured over, and the phrase used
# for it. 30 days keeps the comparison honest: it is not a calendar month.
PACE_WINDOW_DAYS = 30

# The far edge of the pace rule. A goal with years left has no pace to be behind
# yet, and "about KES 11 a month closes the gap" said a decade before the
# deadline is arithmetic without judgement. Such a goal stays quiet until its
# deadline is inside this horizon; the deadline rule then takes over at 14 days.
PACE_HORIZON_DAYS = 365

_SEVERITY_RANK = {"overdue": 0, "due": 1, "soon": 2, "attention": 3}

KIND_PREFERENCE = {
    "deadline": "deadline_alerts",
    "task": "task_reminders",
    "fee": "fee_due_alerts",
    "stock": "low_stock_warnings",
    "savings": "savings_nudges",
}


@dataclass
class Alert:
    """One thing worth looking at, and the record it came from."""

    key: str
    kind: AlertKind
    severity: Severity
    title: str
    detail: str | None
    amount_minor: int | None
    due_on: date | None
    days_out: int | None
    link: str
    # What a period of saving would need to look like, when the alert is about a
    # rate rather than a sum. Paired with period_label so the frontend can say
    # "about X a month" without guessing what X was measured against.
    period_amount_minor: int | None = None
    period_label: str | None = None

    @property
    def sort_value(self) -> tuple[int, int, str]:
        # Overdue first, then the nearest date. An undated alert sorts last
        # within its severity because it has no date to be near.
        return (
            _SEVERITY_RANK[self.severity],
            self.days_out if self.days_out is not None else 10_000,
            self.title,
        )


def _days_out(due: date, today: date) -> int:
    return (due - today).days


def _when_phrase(days: int, noun: str = "due") -> str:
    """Plain words for how far off a date is. Negative means already past."""
    if days == 0:
        return f"{noun} today"
    if days > 0:
        return f"{noun} in {days} day" + ("s" if days != 1 else "")
    late = -days
    return f"{late} day" + ("s" if late != 1 else "") + f" past {noun}"


# --- the five rules ---------------------------------------------------------

def _task_alerts(db: Session, user_id: int, today: date) -> list[Alert]:
    """Open tasks that are past due, due today, or inside their own reminder
    window. remind_before_days null means no early nudge was asked for, so for
    those only the day itself and the overdue period count."""
    rows = db.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.deleted_at.is_(None),
            Task.status.in_(("pending", "in_progress")),
            Task.due_on.isnot(None),
        )
    ).all()
    alerts: list[Alert] = []
    for t in rows:
        assert t.due_on is not None  # guaranteed by the filter
        days = _days_out(t.due_on, today)
        window = t.remind_before_days or 0
        if days > window:
            continue
        parts = [_when_phrase(days)]
        if t.due_time is not None:
            parts.append(f"at {t.due_time:%H:%M}")
        if t.priority and t.priority != "medium":
            parts.append(f"{t.priority} priority")
        if t.recurrence and t.recurrence != "none":
            parts.append(f"repeats {t.recurrence}")
        alerts.append(Alert(
            key=f"task:{t.id}",
            kind="task",
            severity="overdue" if days < 0 else "due",
            title=t.title,
            detail=" · ".join(parts),
            amount_minor=None,
            due_on=t.due_on,
            days_out=days,
            link="/app/tasks",
        ))
    return alerts


def _goal_totals(db: Session, goal_ids: list[int], since: date | None = None) -> dict[int, int]:
    """Contributions per goal, in one grouped query, so a long goal list does
    not cost one query each. `since` narrows to contributions after that date."""
    if not goal_ids:
        return {}
    stmt = select(
        GoalContribution.goal_id,
        func.coalesce(func.sum(GoalContribution.amount_minor), 0),
    ).where(GoalContribution.goal_id.in_(goal_ids))
    if since is not None:
        stmt = stmt.where(GoalContribution.occurred_on > since)
    return {goal_id: int(total or 0) for goal_id, total in db.execute(stmt.group_by(
        GoalContribution.goal_id
    )).all()}


def _deadline_alerts(db: Session, user_id: int, today: date) -> list[Alert]:
    """Active goals whose deadline is past or close. A goal with no deadline
    produces nothing: there is no date to be late against."""
    goals = db.scalars(
        select(Goal).where(
            Goal.user_id == user_id,
            Goal.status == "active",
            Goal.deadline.isnot(None),
        )
    ).all()
    saved = _goal_totals(db, [g.id for g in goals])
    alerts: list[Alert] = []
    for g in goals:
        assert g.deadline is not None  # guaranteed by the filter
        days = _days_out(g.deadline, today)
        if days > DUE_WINDOW_DAYS:
            continue
        parts = [_when_phrase(days, "deadline")]
        amount: int | None = None
        if g.type == "money" and g.target_amount_minor is not None:
            outstanding = max(g.target_amount_minor - saved.get(g.id, 0), 0)
            amount = outstanding or None
            parts.append("nothing saved toward it yet" if not saved.get(g.id, 0)
                         else "partly saved")
        elif g.type == "quantity":
            target = g.target_quantity if g.target_quantity is not None else "?"
            parts.append(f"{g.current_quantity or 0} of {target} collected")
        if g.priority and g.priority != "medium":
            parts.append(f"{g.priority} priority")
        alerts.append(Alert(
            key=f"goal:{g.id}",
            kind="deadline",
            severity="overdue" if days < 0 else "due",
            title=g.name,
            detail=" · ".join(parts),
            amount_minor=amount,
            due_on=g.deadline,
            days_out=days,
            link="/app/goals",
        ))
    return alerts


def _fee_alerts(db: Session, user_id: int, today: date) -> list[Alert]:
    """Fees with something outstanding and a date they are owed by. A fee with
    no due date is left out rather than treated as overdue, and one paid in
    full is silent because the payments say so."""
    fees = db.scalars(
        select(FeeObligation).where(
            FeeObligation.user_id == user_id,
            FeeObligation.deleted_at.is_(None),
        )
    ).all()
    alerts: list[Alert] = []
    for f in fees:
        outstanding = max(f.amount_due_minor - f.amount_paid_minor, 0)
        if outstanding <= 0 or f.due_on is None:
            continue
        days = _days_out(f.due_on, today)
        if days > DUE_WINDOW_DAYS:
            continue
        parts = [_when_phrase(days)]
        if f.amount_paid_minor > 0:
            parts.append("part of it is already paid")
        if f.category:
            parts.append(f.category.replace("_", " "))
        alerts.append(Alert(
            key=f"fee:{f.id}",
            kind="fee",
            severity="overdue" if days < 0 else "due",
            title=f.name,
            detail=" · ".join(parts),
            amount_minor=outstanding,
            due_on=f.due_on,
            days_out=days,
            link="/app/student",
        ))
    return alerts


def _stock_alerts(db: Session, user_id: int) -> list[Alert]:
    """Tracked items below the quantity the user said they want to hold. The
    cost is only carried when a price was entered; when it was not, the alert
    says the price is missing instead of showing a total built on nothing."""
    items = db.scalars(
        select(InventoryItem).where(
            InventoryItem.user_id == user_id,
            InventoryItem.deleted_at.is_(None),
            InventoryItem.target_quantity.isnot(None),
        )
    ).all()
    cat_names = {c.id: c.name for c in db.scalars(
        select(InventoryCategory).where(InventoryCategory.user_id == user_id)
    ).all()}
    alerts: list[Alert] = []
    for item in items:
        assert item.target_quantity is not None  # guaranteed by the filter
        need = item.target_quantity - item.quantity_owned
        if need <= 0:
            continue
        unit = f" {item.unit}" if item.unit else ""
        parts = [
            f"{item.quantity_owned} of {item.target_quantity} held",
            f"{need} more{unit} short",
        ]
        if cat_names.get(item.category_id):
            parts.append(cat_names[item.category_id])
        cost = need * item.estimated_unit_cost_minor \
            if item.estimated_unit_cost_minor is not None else None
        if cost is None:
            parts.append("no price recorded, so no cost is shown")
        alerts.append(Alert(
            key=f"item:{item.id}",
            kind="stock",
            severity="attention",
            title=item.name,
            detail=" · ".join(parts),
            amount_minor=cost,
            due_on=None,
            days_out=None,
            link="/app/inventory",
        ))
    return alerts


def _savings_alerts(db: Session, user_id: int, today: date) -> list[Alert]:
    """Money goals behind their own pace, while there is still time to catch up.

    Two edges keep this rule useful rather than merely true. It is silent inside
    DUE_WINDOW_DAYS, where the deadline rule is already saying the same thing
    more urgently, and silent beyond PACE_HORIZON_DAYS, where a goal so far from
    its date cannot yet be described as slow.

    The rate is the goal's own arithmetic: what is left to save, spread over the
    days its own deadline allows, restated against a 30-day window so it can be
    compared with what actually went in over the last 30 days. Both figures come
    from recorded contributions - nothing here knows about money that arrived by
    some route the user never entered.
    """
    goals = db.scalars(
        select(Goal).where(
            Goal.user_id == user_id,
            Goal.status == "active",
            Goal.type == "money",
            Goal.target_amount_minor.isnot(None),
            Goal.deadline.isnot(None),
        )
    ).all()
    if not goals:
        return []
    goal_ids = [g.id for g in goals]
    saved = _goal_totals(db, goal_ids)
    recent = _goal_totals(db, goal_ids, since=today - timedelta(days=PACE_WINDOW_DAYS))

    alerts: list[Alert] = []
    for g in goals:
        assert g.deadline is not None and g.target_amount_minor is not None  # filtered
        days = _days_out(g.deadline, today)
        if days <= DUE_WINDOW_DAYS or days > PACE_HORIZON_DAYS:
            continue
        outstanding = g.target_amount_minor - saved.get(g.id, 0)
        if outstanding <= 0:
            continue
        needed = round(outstanding * PACE_WINDOW_DAYS / days)
        actual = recent.get(g.id, 0)
        if actual >= needed:
            continue
        window = f"{PACE_WINDOW_DAYS} days"
        detail = (
            f"nothing has gone into it in the last {window}" if actual == 0 else
            f"less than its own deadline asks for went in over the last {window}"
        )
        alerts.append(Alert(
            key=f"goal:{g.id}",
            kind="savings",
            severity="soon",
            title=g.name,
            detail=f"{detail} · deadline {g.deadline:%d %b}",
            amount_minor=outstanding,
            due_on=g.deadline,
            days_out=days,
            link="/app/goals",
            period_amount_minor=needed,
            period_label=f"{PACE_WINDOW_DAYS}-day",
        ))
    return alerts


# --- quiet hours ------------------------------------------------------------

def in_quiet_hours(now: time, start: time | None, end: time | None) -> bool:
    """Whether a wall-clock time falls inside the quiet period. Both ends are
    optional, and a start later than the end means the period runs through
    midnight. Reads the machine's own clock: this app runs on the user's laptop,
    so that clock is already their local time, and no timezone conversion is
    being claimed here."""
    if start is None or end is None or start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end


def quiet_ends_at(now: time, start: time | None, end: time | None) -> time | None:
    """When the quiet period currently running finishes, else None."""
    return end if in_quiet_hours(now, start, end) else None


# --- the entry point --------------------------------------------------------

def build_alerts(db: Session, user: User, pref: NotificationPreference,
                 today: date | None = None, now_time: time | None = None) -> dict:
    """Every alert the user's records support right now.

    The kinds switched off are returned as a list rather than quietly dropped,
    so the page can say "3 switches are off" instead of looking like there is
    nothing to report.
    """
    today = today or date.today()
    now_time = now_time or datetime.now().time()

    producers = {
        "deadline": lambda: _deadline_alerts(db, user.id, today),
        "task": lambda: _task_alerts(db, user.id, today),
        "fee": lambda: _fee_alerts(db, user.id, today),
        "stock": lambda: _stock_alerts(db, user.id),
        "savings": lambda: _savings_alerts(db, user.id, today),
    }
    alerts: list[Alert] = []
    hidden: list[str] = []
    for kind, produce in producers.items():
        if not getattr(pref, KIND_PREFERENCE[kind]):
            hidden.append(kind)
            continue
        alerts.extend(produce())

    alerts.sort(key=lambda a: a.sort_value)
    return {
        "generated_on": today,
        "generated_at": now_time.replace(microsecond=0),
        # The figures leave here as minor units, so the page needs to know which
        # currency they are in. It comes from the profile, not a default.
        "currency": user.currency,
        "alerts": alerts,
        "count": len(alerts),
        "hidden_by_preferences": hidden,
        "in_quiet_hours": in_quiet_hours(now_time, pref.quiet_start, pref.quiet_end),
        "quiet_ends_at": quiet_ends_at(now_time, pref.quiet_start, pref.quiet_end),
        "quiet_start": pref.quiet_start,
        "quiet_end": pref.quiet_end,
    }
