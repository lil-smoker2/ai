"""Task urgency: a fixed, explainable arithmetic - never a learned score.

Priority points (low 0, medium 5, high 10, critical 20) plus three points per
day past the due date, capped at ten days. The tests pin the two weights and
the band each task lands in, and confirm the honest silences: no due date adds
no lateness, a settled task asks for nothing (score 0), and ordering by urgency
is just this same sum read high to low.
"""
from datetime import date, timedelta


def _create(client, headers, **over):
    body = {"title": "Task", "priority": "medium", **over}
    resp = client.post("/api/tasks", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _on(days_from_today):
    return (date.today() + timedelta(days=days_from_today)).isoformat()


def _tasks(client, headers, **params):
    return client.get("/api/tasks", params=params, headers=headers).json()


# --- the sum, on round numbers ------------------------------------------------

def test_priority_alone_when_there_is_no_due_date(client, auth_headers):
    t = _create(client, auth_headers, priority="high")  # no due_on
    # Nothing dated to be late against, so no lateness is invented.
    assert t["urgency"] == {
        "score": 10, "band": "unscheduled", "priority_points": 10,
        "overdue_points": 0,
    }


def test_days_overdue_add_three_points_each(client, auth_headers):
    t = _create(client, auth_headers, priority="medium", due_on=_on(-4))
    # medium 5 + 4 days * 3 = 17, and the overdue flag agrees it is late.
    assert t["urgency"]["overdue_points"] == 12
    assert t["urgency"]["score"] == 17
    assert t["urgency"]["band"] == "overdue"
    assert t["is_overdue"] is True


def test_lateness_stops_counting_at_ten_days(client, auth_headers):
    t = _create(client, auth_headers, priority="critical", due_on=_on(-40))
    # Capped: 10 * 3 = 30, not 120 - a long-abandoned task cannot swamp all.
    assert t["urgency"]["overdue_points"] == 30
    assert t["urgency"]["score"] == 50


def test_due_soon_is_just_the_priority_no_penalty(client, auth_headers):
    t = _create(client, auth_headers, priority="low", due_on=_on(2))
    # Two days out is "due soon" but not late: low adds 0, overdue adds 0.
    assert t["urgency"]["band"] == "due-soon"
    assert t["urgency"]["score"] == 0
    assert t["is_overdue"] is False


def test_far_off_is_scheduled_at_its_priority(client, auth_headers):
    t = _create(client, auth_headers, priority="medium", due_on=_on(30))
    assert t["urgency"]["band"] == "scheduled"
    assert t["urgency"]["score"] == 5


def test_a_settled_task_asks_for_nothing(client, auth_headers):
    t = _create(client, auth_headers, priority="critical", due_on=_on(-8))
    assert t["urgency"]["score"] == 44  # 20 + 24
    done = client.post(f"/api/tasks/{t['id']}/complete", headers=auth_headers).json()
    # Finishing it drops the urgency to zero, so it cannot outrank open work.
    assert done["urgency"] == {
        "score": 0, "band": "settled", "priority_points": 0, "overdue_points": 0,
    }


# --- ordering -----------------------------------------------------------------

def test_urgency_ordering_puts_the_most_pressing_first(client, auth_headers):
    _create(client, auth_headers, title="mild", priority="low", due_on=_on(-5))     # 15
    _create(client, auth_headers, title="big-nowait", priority="critical")          # 20
    _create(client, auth_headers, title="late-and-critical", priority="high",
            due_on=_on(-20))                                                        # 40
    order = [t["title"] for t in _tasks(client, auth_headers, sort="urgency")]
    assert order == ["late-and-critical", "big-nowait", "mild"]


def test_default_ordering_is_still_by_due_date(client, auth_headers):
    _create(client, auth_headers, title="no-date", priority="critical")
    _create(client, auth_headers, title="due-today", due_on=_on(0))
    _create(client, auth_headers, title="due-first", due_on=_on(-3))
    order = [t["title"] for t in _tasks(client, auth_headers)]
    # Undated sorts last (nullslast); earliest due first - unchanged behaviour.
    assert order == ["due-first", "due-today", "no-date"]
