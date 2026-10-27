"""Tasks & Reminders tests: CRUD, status math, overdue, ownership, soft delete."""
from datetime import date, timedelta


def _create(client, headers, **over):
    body = {"title": "Buy textbooks", **over}
    return client.post("/api/tasks", json=body, headers=headers).json()


def test_create_task_defaults(client, auth_headers):
    t = _create(client, auth_headers)
    assert t["status"] == "pending"
    assert t["priority"] == "medium"
    assert t["recurrence"] == "none"
    assert t["is_overdue"] is False


def test_overdue_computed_only_for_open_tasks(client, auth_headers):
    yday = (date.today() - timedelta(days=1)).isoformat()
    t = _create(client, auth_headers, due_on=yday)
    assert t["is_overdue"] is True

    done = client.post(f"/api/tasks/{t['id']}/complete", headers=auth_headers).json()
    assert done["status"] == "completed"
    assert done["completed_at"] is not None
    # Completing clears the overdue flag without touching any money/fee state.
    assert done["is_overdue"] is False


def test_update_status_sets_and_clears_completed_at(client, auth_headers):
    t = _create(client, auth_headers)
    completed = client.put(
        f"/api/tasks/{t['id']}", json={"status": "completed"}, headers=auth_headers
    ).json()
    assert completed["completed_at"] is not None
    reopened = client.put(
        f"/api/tasks/{t['id']}", json={"status": "in_progress"}, headers=auth_headers
    ).json()
    assert reopened["completed_at"] is None


def test_snooze_pushes_due_date(client, auth_headers):
    t = _create(client, auth_headers, due_on=date.today().isoformat())
    snoozed = client.post(
        f"/api/tasks/{t['id']}/snooze", json={"days": 5}, headers=auth_headers
    ).json()
    assert snoozed["due_on"] == (date.today() + timedelta(days=5)).isoformat()


def test_complete_task_does_not_touch_transactions(client, auth_headers):
    t = _create(client, auth_headers, title="Reminder to pay fees")
    client.post(f"/api/tasks/{t['id']}/complete", headers=auth_headers)
    txns = client.get("/api/transactions", headers=auth_headers).json()["transactions"]
    assert txns == []  # completing a reminder is not proof of payment


def test_soft_delete_requires_confirm_and_hides(client, auth_headers):
    t = _create(client, auth_headers)
    anon = client.delete(f"/api/tasks/{t['id']}")
    assert anon.status_code == 401  # unauthenticated
    resp = client.delete(f"/api/tasks/{t['id']}", headers=auth_headers)
    assert resp.status_code == 400  # missing confirm
    ok = client.delete(
        f"/api/tasks/{t['id']}", headers=auth_headers, params={"confirm": "true"}
    )
    assert ok.status_code == 204
    assert client.get("/api/tasks", headers=auth_headers).json() == []


def test_status_filter(client, auth_headers):
    _create(client, auth_headers, status="pending")
    _create(client, auth_headers, status="completed")
    pending = client.get(
        "/api/tasks", headers=auth_headers, params={"status": "pending"}
    ).json()
    assert len(pending) == 1


def test_cannot_link_another_users_goal(client, auth_headers, second_user_headers):
    goal = client.post(
        "/api/goals",
        json={"name": "Other laptop", "type": "money", "target_amount_minor": 500000},
        headers=second_user_headers,
    ).json()
    resp = client.post(
        "/api/tasks",
        json={"title": "Steal goal", "goal_id": goal["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_from_goal_creates_proposed_task(client, auth_headers):
    goal = client.post(
        "/api/goals",
        json={"name": "New phone", "type": "money", "target_amount_minor": 4000000},
        headers=auth_headers,
    ).json()
    t = client.post(f"/api/tasks/from-goal/{goal['id']}", headers=auth_headers).json()
    assert t["status"] == "proposed"
    assert t["goal_id"] == goal["id"]


def test_cross_user_isolation(client, auth_headers, second_user_headers):
    t = _create(client, auth_headers)
    resp = client.get(f"/api/tasks/{t['id']}", headers=second_user_headers)
    assert resp.status_code == 404


def test_requires_auth(client):
    assert client.get("/api/tasks").status_code == 401
