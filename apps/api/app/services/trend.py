"""Which way the saved net worth is moving, read from the saved snapshots.

The snapshots are the only input: each day's recorded total, exactly as it was
saved. A day whose total was unknown (an owned item without a price) is a gap
in the record - it is counted as a gap and left out of the arithmetic, never
filled in with an assumed figure.

Two plain readings are reported, both explainable from the rows shown on the
page:

* the least-squares slope of the known totals against the day they were
  recorded, in integer minor units per day;
* the change from the first to the last known day, and a moving average of up
  to the most recent points.

"Steady" is not a vibe: a slope counts as moving only once it clears a band of
half a percent of the median total per day (or one pesa a day, whichever is
bigger). Below that band the record genuinely does not show a direction, and
that is what is said. Fewer than MIN_KNOWN_DAYS known days and there is no
trend at all - the answer is silence, not a line through two points.
"""
from __future__ import annotations

from datetime import date
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.valuation import NetWorthSnapshot
from app.models.user import User

# A slope needs more than two points; through two points any line is exact and
# says nothing about direction.
MIN_KNOWN_DAYS = 3

# Up to this many of the most recent known days feed the moving average.
MOVING_WINDOW = 4

# The reading covers at most this many saved days - the same span the page's
# history table shows, so every point on the line is a row the reader can see.
MAX_TREND_DAYS = 12


def _slope_per_day(points: list[tuple[int, int]]) -> float:
    """Least-squares slope of value (y-axis, index 1) against x (index 0)."""
    n = len(points)
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    denominator = sum((x - mean_x) ** 2 for x, _ in points)
    if denominator == 0:
        return 0.0
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in points)
    return numerator / denominator


def describe(db: Session, user: User,
             until: date | None = None) -> dict | None:
    """The direction the saved net worth has been moving in, or None.

    None means the record cannot support a reading yet - fewer than
    MIN_KNOWN_DAYS complete days - and the caller must present no trend rather
    than an invented one.
    """
    until = until or date.today()
    rows = db.scalars(
        select(NetWorthSnapshot)
        .where(
            NetWorthSnapshot.user_id == user.id,
            NetWorthSnapshot.on_date <= until,
        )
        .order_by(NetWorthSnapshot.on_date)
    ).all()[-MAX_TREND_DAYS:]

    known = [(r.on_date, r.net_worth_minor) for r in rows
             if r.complete and r.net_worth_minor is not None]
    if len(known) < MIN_KNOWN_DAYS:
        return None

    base = known[0][0]
    # Day offsets keep the regression in whole days; snapshots are one per day.
    points = [((d - base).days, value) for d, value in known]
    slope = _slope_per_day(points)

    # "Moving" must clear a band, not merely be nonzero: half a percent of
    # the median total per day, or one pesa a day, whichever is bigger.
    band = max(100, 0.005 * median(value for _, value in known))
    if slope > band:
        direction = "building"
    elif slope < -band:
        direction = "declining"
    else:
        direction = "steady"

    window = [value for _, value in known[-MOVING_WINDOW:]]
    return {
        "from_date": known[0][0],
        "to_date": known[-1][0],
        "known_days": len(known),
        "gap_days": len(rows) - len(known),
        "slope_minor_per_day": round(slope),
        "change_minor": known[-1][1] - known[0][1],
        "recent_average_minor": round(sum(window) / len(window)),
        "direction": direction,
    }
