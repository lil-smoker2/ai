"""Goal completion projections: an ETA only where contributions support one.

A projection is the goal's own recorded saving read forward. Every case here
asserts either silence (no contributions, stale contributions, a finished or
paused goal -> no date) or exact arithmetic on round numbers, so the projected
date, the per-day pace in minor units, and the deadline comparison are all
checkable facts rather than approximations.
"""
from datetime import date, timedelta

WINDOW = 120  # mirrors forecasting.FORECAST_WINDOW_DAYS


def _goal(client, headers, **over):
    body = {"name": "Emergency fund", "type": "money",
            "target_amount_minor": 6000000, **over}
    resp = client.post("/api/goals", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _save(client, headers, goal_id, amount_minor, days_ago):
    body = {
        "amount_minor": amount_minor,
        "occurred_on": (date.today() - timedelta(days=days_ago)).isoformat(),
    }
    resp = client.post(f"/api/goals/{goal_id}/contributions",
                       json=body, headers=headers)
    assert resp.status_code == 201, resp.text


def _fetch(client, headers, goal_id):
    return client.get(f"/api/goals/{goal_id}", headers=headers).json()


# --- silence: no recorded saving, no date -----------------------------------

def test_a_goal_without_contributions_has_no_eta(client, auth_headers):
    goal = _goal(client, auth_headers)
    assert goal["projection"] is None


def test_a_fully_funded_goal_needs_no_projection(client, auth_headers):
    goal = _goal(client, auth_headers, target_amount_minor=100000)
    _save(client, auth_headers, goal["id"], 100000, days_ago=3)
    assert _fetch(client, auth_headers, goal["id"])["projection"] is None


def test_a_completed_goal_has_no_projection(client, auth_headers):
    goal = _goal(client, auth_headers, target_amount_minor=100000)
    _save(client, auth_headers, goal["id"], 100000, days_ago=3)
    client.post(f"/api/goals/{goal['id']}/complete?force=true",
                headers=auth_headers)
    assert _fetch(client, auth_headers, goal["id"])["projection"] is None


def test_a_paused_goal_is_not_projected(client, auth_headers):
    goal = _goal(client, auth_headers)
    _save(client, auth_headers, goal["id"], 1000000, days_ago=4)
    client.post(f"/api/goals/{goal['id']}/pause", headers=auth_headers)
    assert _fetch(client, auth_headers, goal["id"])["projection"] is None


# --- a real pace, projected exactly ------------------------------------------

def test_eta_comes_from_the_observed_saving_pace(client, auth_headers):
    goal = _goal(client, auth_headers)  # target 6,000,000
    _save(client, auth_headers, goal["id"], 1000000, days_ago=8)
    _save(client, auth_headers, goal["id"], 1000000, days_ago=4)
    # saved 2,000,000 -> remaining 4,000,000; pace 2,000,000 over the 8 days
    # since the first contribution = 250,000/day, so 4,000,000 needs 16 days.
    p = _fetch(client, auth_headers, goal["id"])["projection"]
    assert p["amount_per_day_minor"] == 250000
    assert p["contribution_count"] == 2
    assert p["window_days"] == 8
    assert p["days_to_target"] == 16
    assert p["projected_on"] == (date.today() + timedelta(days=16)).isoformat()
    assert p["status"] == "no_deadline"


def test_deadline_comparison_uses_the_projected_date(client, auth_headers):
    good = _goal(client, auth_headers,
                 deadline=str(date.today() + timedelta(days=20)))
    _save(client, auth_headers, good["id"], 1000000, days_ago=8)
    _save(client, auth_headers, good["id"], 1000000, days_ago=4)
    # projected in 16 days, deadline in 20 -> the pace covers it
    assert _fetch(client, auth_headers, good["id"])["projection"]["status"] \
        == "on_track"

    late = _goal(client, auth_headers,
                 deadline=str(date.today() + timedelta(days=4)))
    _save(client, auth_headers, late["id"], 1000000, days_ago=8)
    _save(client, auth_headers, late["id"], 1000000, days_ago=4)
    # same pace, but the projection lands after the deadline
    assert _fetch(client, auth_headers, late["id"])["projection"]["status"] \
        == "after_deadline"


def test_saving_that_stopped_is_not_counted_as_pace(client, auth_headers):
    goal = _goal(client, auth_headers)
    _save(client, auth_headers, goal["id"], 1000000, days_ago=WINDOW + 30)
    # The only contribution is outside the window: saved total still counts
    # toward progress, but there is no recent pace to read forward.
    assert _fetch(client, auth_headers, goal["id"])["projection"] is None


def test_quantity_goal_projects_only_what_its_history_supports(client, auth_headers):
    goal = client.post(
        "/api/goals",
        json={"name": "Laptop", "type": "quantity", "target_quantity": 1,
              "current_quantity": 0, "estimated_unit_cost_minor": 4000000},
        headers=auth_headers,
    ).json()
    _save(client, auth_headers, goal["id"], 1000000, days_ago=4)
    # remaining cost 4,000,000 at 1,000,000 over 4 days = 250,000/day -> 16
    p = _fetch(client, auth_headers, goal["id"])["projection"]
    assert p["amount_per_day_minor"] == 250000
    assert p["days_to_target"] == 16
    assert p["contribution_count"] == 1
