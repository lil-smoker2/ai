"""Notification preferences tests: default create, update, per-user isolation."""


def test_get_creates_default_all_enabled(client, auth_headers):
    pref = client.get("/api/notifications/preferences", headers=auth_headers).json()
    assert pref["deadline_alerts"] is True
    assert pref["task_reminders"] is True
    assert pref["low_stock_warnings"] is True
    assert pref["savings_nudges"] is True
    assert pref["fee_due_alerts"] is True
    assert pref["quiet_start"] is None


def test_update_partial_persists(client, auth_headers):
    updated = client.put(
        "/api/notifications/preferences",
        json={"savings_nudges": False, "quiet_start": "22:30"},
        headers=auth_headers,
    ).json()
    assert updated["savings_nudges"] is False
    assert updated["quiet_start"] == "22:30:00"
    # Untouched flags keep their prior value (deadline_alerts unchanged).
    assert updated["deadline_alerts"] is True

    # Re-read reflects the saved state, not a fresh default.
    again = client.get("/api/notifications/preferences", headers=auth_headers).json()
    assert again["savings_nudges"] is False


def test_preferences_are_isolated_per_user(client, auth_headers, second_user_headers):
    client.put(
        "/api/notifications/preferences",
        json={"task_reminders": False},
        headers=auth_headers,
    )
    other = client.get(
        "/api/notifications/preferences", headers=second_user_headers
    ).json()
    assert other["task_reminders"] is True


def test_requires_auth(client):
    assert client.get("/api/notifications/preferences").status_code == 401
