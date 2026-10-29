"""Net-worth trend: a direction only once the saved record can support one.

The trend is read straight off the NetWorthSnapshot rows - the same table the
page shows. These tests seed snapshots directly, because that is exactly what
days of recorded history are. The readings are checked on day-spacing of one
and two so the least-squares slope is exact: any line through equally spaced
points on a straight path has that path's slope.
"""
from datetime import date, timedelta

from app.core.database import SessionLocal
from app.models.user import User
from app.models.valuation import NetWorthSnapshot


def _user(db):
    return db.query(User).filter_by(email="test@example.com").first()


def _seed(db, user_id, series):
    """series: list of (days_ago, net_worth_minor) or (days_ago, None) for a gap."""
    today = date.today()
    for days_ago, value in series:
        db.add(NetWorthSnapshot(
            user_id=user_id,
            on_date=today - timedelta(days=days_ago),
            net_worth_minor=value,
            priced_value_minor=value or 0,
            valued_items=1,
            unpriced_items=0 if value is not None else 1,
            complete=value is not None,
        ))
    db.commit()


def _valuation(client, headers):
    resp = client.get("/api/networth", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _trend_of(client, headers, series):
    with SessionLocal() as db:
        _seed(db, _user(db).id, series)
    return _valuation(client, headers)["trend"]


# --- silence: a record too thin to have a direction ---------------------------

def test_a_lone_recorded_day_shows_no_trend(client, auth_headers):
    # A fresh account records today's zero as its first day; one day is not a
    # direction, so the response carries no trend rather than a flat line.
    assert _valuation(client, auth_headers)["trend"] is None


def test_two_days_are_still_not_a_reading(client, auth_headers):
    # Two recorded days, one of them today so the page's own "record today on
    # first look" adds nothing: two known days is below MIN_KNOWN_DAYS.
    trend = _trend_of(client, auth_headers, [(1, 100000), (0, 200000)])
    assert trend is None


# --- a real reading, exact on round spacing ------------------------------------

def test_a_steady_climb_reads_as_building(client, auth_headers):
    trend = _trend_of(client, auth_headers, [(2, 100000), (1, 150000), (0, 200000)])
    assert trend["direction"] == "building"
    assert trend["known_days"] == 3
    assert trend["gap_days"] == 0
    assert trend["change_minor"] == 100000
    assert trend["slope_minor_per_day"] == 50000
    assert trend["recent_average_minor"] == 150000
    assert trend["from_date"] == (date.today() - timedelta(days=2)).isoformat()
    assert trend["to_date"] == date.today().isoformat()


def test_a_steady_fall_reads_as_declining(client, auth_headers):
    trend = _trend_of(client, auth_headers, [(2, 200000), (1, 150000), (0, 100000)])
    assert trend["direction"] == "declining"
    assert trend["slope_minor_per_day"] == -50000
    # The change is the signed truth of where the record ended up.
    assert trend["change_minor"] == -100000


def test_a_record_that_barely_moves_is_reported_steady(client, auth_headers):
    trend = _trend_of(client, auth_headers, [(2, 100000), (1, 100010), (0, 100020)])
    # slope 10/day is far under the band (0.5% of ~100000 = 500): honest steady.
    assert trend["direction"] == "steady"
    assert trend["slope_minor_per_day"] == 10
    assert trend["change_minor"] == 20


def test_the_moving_average_covers_the_four_most_recent_days(client, auth_headers):
    trend = _trend_of(client, auth_headers,
                      [(4, 100000), (3, 100000), (2, 100000), (1, 200000), (0, 300000)])
    assert trend["known_days"] == 5
    # Last four: 100000 + 100000 + 200000 + 300000 over 4.
    assert trend["recent_average_minor"] == 175000


# --- gaps: unknown days are counted, never filled in --------------------------

def test_unknown_days_are_gaps_and_stay_out_of_the_math(client, auth_headers):
    trend = _trend_of(client, auth_headers,
                      [(3, 100000), (2, 150000), (1, 200000), (0, None)])
    assert trend["known_days"] == 3
    assert trend["gap_days"] == 1
    # Read only from the known days: still a 50000/day slope, and the gap did
    # not bend it - no figure was invented for the missing day.
    assert trend["slope_minor_per_day"] == 50000
    assert trend["change_minor"] == 100000


def test_three_gaps_and_nothing_else_stays_silent(client, auth_headers):
    assert _trend_of(client, auth_headers, [(3, None), (2, None), (1, None)]) is None
