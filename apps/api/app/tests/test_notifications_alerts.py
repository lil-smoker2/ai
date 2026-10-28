"""The derived alerts: what fires, what stays silent, and what the switches hide.

Every rule in app.services.alerts is about *not* saying something the records do
not support, so most of these tests assert absence: an unrecorded date, an
unknown price or a paid-off fee must produce nothing rather than a plausible
looking alert.
"""
from datetime import date, datetime, timedelta

# --- helpers ---------------------------------------------------------------

def _alerts(client, headers):
    resp = client.get("/api/notifications/alerts", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _kinds(payload):
    return {a["kind"] for a in payload["alerts"]}


def _one(payload, key):
    """The single alert with this key, or a failure naming what was there."""
    matches = [a for a in payload["alerts"] if a["key"] == key]
    assert len(matches) == 1, f"expected one {key}, got {[m['key'] for m in payload['alerts']]}"
    return matches[0]


def _task(client, headers, **over):
    body = {"title": "Pay tuition", **over}
    return client.post("/api/tasks", json=body, headers=headers).json()


def _goal(client, headers, **over):
    body = {"name": "Laptop fund", "type": "money", "target_amount_minor": 600000, **over}
    return client.post("/api/goals", json=body, headers=headers).json()


def _clothing_category(client, headers):
    cats = client.get("/api/inventory/categories", headers=headers).json()
    return next(c for c in cats if c["name"].lower() == "clothing")


def _item(client, headers, **over):
    body = {"name": "Chinos", "quantity_owned": 1, "target_quantity": 3,
            "category_id": _clothing_category(client, headers)["id"], **over}
    return client.post("/api/inventory/items", json=body, headers=headers).json()


def _fee(client, headers, **over):
    body = {"name": "Semester tuition", "category": "tuition",
            "amount_due_minor": 100000, **over}
    return client.post("/api/student/fees", json=body, headers=headers).json()


# --- silence: the rule that matters most -----------------------------------

def test_a_fresh_account_has_nothing_to_report(client, auth_headers):
    payload = _alerts(client, auth_headers)
    assert payload["alerts"] == []
    assert payload["count"] == 0
    # Nothing is hidden either, so the page can say "records are quiet" rather
    # than "your switches hid something".
    assert payload["hidden_by_preferences"] == []
    assert payload["generated_on"] == date.today().isoformat()


def test_a_task_with_no_date_can_never_be_late(client, auth_headers):
    _task(client, auth_headers)  # due_on omitted
    assert _alerts(client, auth_headers)["alerts"] == []


def test_a_goal_with_no_deadline_is_silent(client, auth_headers):
    _goal(client, auth_headers)
    assert _alerts(client, auth_headers)["alerts"] == []


def test_a_fee_with_no_due_date_is_not_treated_as_overdue(client, auth_headers):
    _fee(client, auth_headers)
    payload = _alerts(client, auth_headers)
    assert _kinds(payload) == set()
    assert payload["count"] == 0


def test_an_item_with_no_target_quantity_is_not_a_shortage(client, auth_headers):
    _item(client, auth_headers, target_quantity=None)
    assert _alerts(client, auth_headers)["alerts"] == []


# --- tasks -----------------------------------------------------------------

def test_an_overdue_task_alerts(client, auth_headers):
    yday = (date.today() - timedelta(days=1)).isoformat()
    t = _task(client, auth_headers, due_on=yday)
    alert = _one(_alerts(client, auth_headers), f"task:{t['id']}")
    assert alert["kind"] == "task"
    assert alert["severity"] == "overdue"
    assert "1 day past due" in alert["detail"]
    assert alert["link"] == "/app/tasks"


def test_completing_a_task_stops_the_alert(client, auth_headers):
    yday = (date.today() - timedelta(days=1)).isoformat()
    t = _task(client, auth_headers, due_on=yday)
    assert _alerts(client, auth_headers)["count"] == 1
    client.put(f"/api/tasks/{t['id']}", json={"status": "completed"},
               headers=auth_headers)
    # Nothing is stored, so a resolved thing is simply gone from the list.
    assert _alerts(client, auth_headers)["alerts"] == []


def test_a_task_without_a_reminder_window_waits_for_its_day(client, auth_headers):
    soon = (date.today() + timedelta(days=5)).isoformat()
    _task(client, auth_headers, due_on=soon)
    assert _alerts(client, auth_headers)["alerts"] == []

    today = date.today().isoformat()
    _task(client, auth_headers, title="Due today", due_on=today)
    payload = _alerts(client, auth_headers)
    assert [a["title"] for a in payload["alerts"]] == ["Due today"]
    assert "due today" in payload["alerts"][0]["detail"]


def test_a_reminder_window_lets_a_task_alert_early(client, auth_headers):
    in_five = (date.today() + timedelta(days=5)).isoformat()
    t = _task(client, auth_headers, due_on=in_five, remind_before_days=7)
    alert = _one(_alerts(client, auth_headers), f"task:{t['id']}")
    assert alert["severity"] == "due"
    assert "due in 5 days" in alert["detail"]


def test_a_proposed_task_is_not_a_reminder(client, auth_headers):
    """Assistant drafts await confirmation; nagging about them would be wrong."""
    yday = (date.today() - timedelta(days=1)).isoformat()
    _task(client, auth_headers, due_on=yday, status="proposed")
    assert _alerts(client, auth_headers)["alerts"] == []


# --- goal deadlines --------------------------------------------------------

def test_a_goal_deadline_alerts_only_once_it_is_close(client, auth_headers):
    far = _goal(client, auth_headers, type="custom", target_amount_minor=None,
                deadline=(date.today() + timedelta(days=20)).isoformat())
    assert _alerts(client, auth_headers)["alerts"] == []

    near = _goal(client, auth_headers, name="Rent", type="custom",
                 target_amount_minor=None,
                 deadline=(date.today() + timedelta(days=3)).isoformat())
    alert = _one(_alerts(client, auth_headers), f"goal:{near['id']}")
    assert alert["kind"] == "deadline"
    assert "deadline in 3 days" in alert["detail"]
    assert far["id"] is not None  # the distant goal stays out of the list


def test_an_overdue_goal_sorts_before_one_that_is_merely_due(client, auth_headers):
    _goal(client, auth_headers, name="Soon", type="custom", target_amount_minor=None,
          deadline=(date.today() + timedelta(days=2)).isoformat())
    _goal(client, auth_headers, name="Late", type="custom", target_amount_minor=None,
          deadline=(date.today() - timedelta(days=2)).isoformat())
    titles = [a["title"] for a in _alerts(client, auth_headers)["alerts"]]
    assert titles == ["Late", "Soon"]


# --- fees ------------------------------------------------------------------

def test_a_fee_alerts_for_what_is_still_owed(client, auth_headers):
    due_soon = (date.today() + timedelta(days=3)).isoformat()
    fee = _fee(client, auth_headers, due_on=due_soon)
    client.post(f"/api/student/fees/{fee['id']}/payments",
                json={"amount_minor": 40000, "idempotency_key": "pay-1"},
                headers=auth_headers)

    alert = _one(_alerts(client, auth_headers), f"fee:{fee['id']}")
    assert alert["amount_minor"] == 60000
    assert "part of it is already paid" in alert["detail"]
    assert alert["link"] == "/app/student"


def test_a_fee_paid_in_full_goes_quiet(client, auth_headers):
    due_soon = (date.today() + timedelta(days=3)).isoformat()
    fee = _fee(client, auth_headers, due_on=due_soon)
    client.post(f"/api/student/fees/{fee['id']}/payments",
                json={"amount_minor": 100000, "idempotency_key": "pay-all"},
                headers=auth_headers)
    assert _alerts(client, auth_headers)["alerts"] == []


# --- stock -----------------------------------------------------------------

def test_a_shortage_without_a_price_shows_no_cost(client, auth_headers):
    item = _item(client, auth_headers, estimated_unit_cost_minor=None)
    alert = _one(_alerts(client, auth_headers), f"item:{item['id']}")
    assert alert["amount_minor"] is None
    assert "no price recorded, so no cost is shown" in alert["detail"]


def test_a_shortage_with_a_price_states_the_real_gap(client, auth_headers):
    item = _item(client, auth_headers, estimated_unit_cost_minor=50000)
    alert = _one(_alerts(client, auth_headers), f"item:{item['id']}")
    # 2 short at 500.00 each. Minor units, never a formatted string.
    assert alert["amount_minor"] == 100000
    assert "2 more short" in alert["detail"]


def test_an_item_at_its_target_is_not_a_warning(client, auth_headers):
    _item(client, auth_headers, quantity_owned=3, target_quantity=3)
    assert _alerts(client, auth_headers)["alerts"] == []


# --- savings pace ----------------------------------------------------------

def test_a_money_goal_behind_its_own_pace_states_the_rate(client, auth_headers):
    in_60_days = (date.today() + timedelta(days=60)).isoformat()
    goal = _goal(client, auth_headers, deadline=in_60_days)  # 600000 target
    alert = _one(_alerts(client, auth_headers), f"goal:{goal['id']}")
    assert alert["kind"] == "savings"
    assert alert["amount_minor"] == 600000
    # Nothing saved, 60 days left: 600000 * 30 / 60 per 30-day window.
    assert alert["period_amount_minor"] == 300000
    assert alert["period_label"] == "30-day"
    assert "nothing has gone into it" in alert["detail"]


def test_a_goal_keeping_its_pace_gets_left_alone(client, auth_headers):
    in_60_days = (date.today() + timedelta(days=60)).isoformat()
    goal = _goal(client, auth_headers, deadline=in_60_days)
    client.post(f"/api/goals/{goal['id']}/contributions",
                json={"amount_minor": 300000,
                      "occurred_on": date.today().isoformat()},
                headers=auth_headers)
    assert _alerts(client, auth_headers)["alerts"] == []


def test_a_goal_years_from_its_deadline_is_not_called_slow(client, auth_headers):
    """Found by running the rule against real data: a goal dated 2036 produced
    "about KES 11.31 a month closes the gap". Arithmetically true, and worthless
    as something to tell a person today."""
    far = (date.today() + timedelta(days=900)).isoformat()
    _goal(client, auth_headers, deadline=far)
    assert _alerts(client, auth_headers)["alerts"] == []


def test_a_goal_inside_the_horizon_still_alerts(client, auth_headers):
    inside = (date.today() + timedelta(days=300)).isoformat()
    goal = _goal(client, auth_headers, deadline=inside)
    alert = _one(_alerts(client, auth_headers), f"goal:{goal['id']}")
    assert alert["kind"] == "savings"
    # 600000 spread over 300 days is 60000 per 30-day window.
    assert alert["period_amount_minor"] == 60000


def test_a_contribution_outside_the_window_does_not_count_as_pace(client, auth_headers):
    in_60_days = (date.today() + timedelta(days=60)).isoformat()
    goal = _goal(client, auth_headers, deadline=in_60_days)
    client.post(f"/api/goals/{goal['id']}/contributions",
                json={"amount_minor": 500000,
                      "occurred_on": (date.today() - timedelta(days=45)).isoformat()},
                headers=auth_headers)
    # Saved total is 500000, so the gap is 100000 over 60 days: 50000 per 30
    # days asked for, nothing in the last 30. Still a nudge, but a smaller one.
    alert = _one(_alerts(client, auth_headers), f"goal:{goal['id']}")
    assert alert["amount_minor"] == 100000
    assert alert["period_amount_minor"] == 50000


def test_deadline_and_pace_never_both_fire_for_one_goal(client, auth_headers):
    """Inside the deadline window the deadline rule speaks; the pace rule is
    silent, so one goal cannot produce two entries about one problem."""
    in_5_days = (date.today() + timedelta(days=5)).isoformat()
    goal = _goal(client, auth_headers, deadline=in_5_days)
    payload = _alerts(client, auth_headers)
    mine = [a for a in payload["alerts"] if a["key"] == f"goal:{goal['id']}"]
    assert [a["kind"] for a in mine] == ["deadline"]


# --- money never becomes prose ---------------------------------------------

def test_no_amount_is_baked_into_a_sentence(client, auth_headers):
    due_soon = (date.today() + timedelta(days=3)).isoformat()
    _fee(client, auth_headers, due_on=due_soon)
    _item(client, auth_headers, estimated_unit_cost_minor=50000)
    for alert in _alerts(client, auth_headers)["alerts"]:
        detail = alert["detail"] or ""
        assert "KES" not in detail
        # Minor units leaking into prose would print a six-figure number.
        assert "100000" not in detail and "50000" not in detail


def test_the_currency_of_the_figures_travels_with_them(client, auth_headers):
    due_soon = (date.today() + timedelta(days=3)).isoformat()
    fee = _fee(client, auth_headers, due_on=due_soon)
    assert _alerts(client, auth_headers)["currency"] == "KES"

    client.patch("/api/auth/me", json={"currency": "UGX"}, headers=auth_headers)
    payload = _alerts(client, auth_headers)
    # The amount is still minor units and still the same number; only the name
    # of its currency moves, and it moves from the profile, not a default.
    assert payload["currency"] == "UGX"
    assert _one(payload, f"fee:{fee['id']}")["amount_minor"] == 100000


# --- the switches actually control the list --------------------------------

def test_switching_a_kind_off_hides_it_and_says_so(client, auth_headers):
    yday = (date.today() - timedelta(days=1)).isoformat()
    _task(client, auth_headers, due_on=yday)
    assert _kinds(_alerts(client, auth_headers)) == {"task"}

    resp = client.put("/api/notifications/preferences",
                      json={"task_reminders": False}, headers=auth_headers)
    assert resp.status_code == 200
    payload = _alerts(client, auth_headers)
    assert payload["alerts"] == []
    assert payload["hidden_by_preferences"] == ["task"]


def test_one_switch_does_not_silence_another(client, auth_headers):
    yday = (date.today() - timedelta(days=1)).isoformat()
    _task(client, auth_headers, due_on=yday)
    _fee(client, auth_headers, due_on=yday)
    client.put("/api/notifications/preferences", json={"task_reminders": False},
               headers=auth_headers)
    assert _kinds(_alerts(client, auth_headers)) == {"fee"}


# --- quiet hours -----------------------------------------------------------

def test_quiet_hours_that_wrap_past_midnight(client, auth_headers):
    from app.services.alerts import in_quiet_hours

    night = datetime.strptime("22:00", "%H:%M").time()
    morning = datetime.strptime("06:00", "%H:%M").time()
    assert in_quiet_hours(datetime.strptime("23:30", "%H:%M").time(), night, morning)
    assert in_quiet_hours(datetime.strptime("03:00", "%H:%M").time(), night, morning)
    assert not in_quiet_hours(datetime.strptime("07:00", "%H:%M").time(), night, morning)
    # One end missing, or both the same, is no quiet period at all.
    assert not in_quiet_hours(night, night, None)
    assert not in_quiet_hours(night, night, night)


def test_quiet_hours_hide_the_count_not_the_list(client, auth_headers):
    yday = (date.today() - timedelta(days=1)).isoformat()
    _task(client, auth_headers, due_on=yday)

    now = datetime.now()
    start = (now - timedelta(hours=1)).strftime("%H:%M")
    end = (now + timedelta(hours=1)).strftime("%H:%M")
    client.put("/api/notifications/preferences",
               json={"quiet_start": start, "quiet_end": end}, headers=auth_headers)

    payload = _alerts(client, auth_headers)
    assert payload["in_quiet_hours"] is True
    # The list is still there: quiet hours stop an interruption, and this app
    # has none to stop, so only the sidebar badge goes quiet.
    assert payload["count"] == 1
    # Serialised as HH:MM:SS by pydantic, so compare the part the test chose.
    assert payload["quiet_ends_at"][:5] == end


# --- ownership -------------------------------------------------------------

def test_alerts_come_from_your_own_records_only(client, auth_headers, second_user_headers):
    yday = (date.today() - timedelta(days=1)).isoformat()
    mine = _task(client, auth_headers, title="My task", due_on=yday)
    theirs = _task(client, second_user_headers, title="Their task", due_on=yday)

    payload = _alerts(client, auth_headers)
    keys = [a["key"] for a in payload["alerts"]]
    assert keys == [f"task:{mine['id']}"]
    assert f"task:{theirs['id']}" not in keys
