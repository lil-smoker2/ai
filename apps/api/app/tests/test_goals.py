"""Goal calculations: savings, quantity targets, deadline-aware planning."""
from datetime import date, timedelta


def _money_goal(client, headers, **overrides):
    body = {"name": "Emergency fund", "type": "money",
            "target_amount_minor": 6000000, "priority": "high"}
    body.update(overrides)
    return client.post("/api/goals", json=body, headers=headers).json()


def test_money_goal_progress(client, auth_headers):
    goal = _money_goal(client, auth_headers)
    assert goal["amount_saved_minor"] == 0
    assert goal["remaining_amount_minor"] == 6000000

    client.post(f"/api/goals/{goal['id']}/contributions",
                json={"amount_minor": 1500000}, headers=auth_headers)
    client.post(f"/api/goals/{goal['id']}/contributions",
                json={"amount_minor": 500000}, headers=auth_headers)

    goal = client.get(f"/api/goals/{goal['id']}", headers=auth_headers).json()
    assert goal["amount_saved_minor"] == 2000000
    assert goal["remaining_amount_minor"] == 4000000


def test_quantity_goal_cost(client, auth_headers):
    goal = client.post(
        "/api/goals",
        json={"name": "Wardrobe", "type": "quantity", "target_quantity": 20,
              "current_quantity": 5, "estimated_unit_cost_minor": 150000},
        headers=auth_headers,
    ).json()
    assert goal["remaining_quantity"] == 15
    assert goal["estimated_remaining_cost_minor"] == 15 * 150000


def test_required_monthly_saving_rounds_up(client, auth_headers):
    today = date.today()
    deadline = today + timedelta(days=91)  # ~3 months
    goal = _money_goal(client, auth_headers, deadline=str(deadline))
    client.post(f"/api/goals/{goal['id']}/contributions",
                json={"amount_minor": 3000000}, headers=auth_headers)
    goal = client.get(f"/api/goals/{goal['id']}", headers=auth_headers).json()
    assert goal["deadline_state"] == "ok"
    months = (deadline - today).days // 30.44
    assert goal["required_monthly_saving_minor"] >= int(3000000 // months)


def test_past_deadline_never_divides_by_zero(client, auth_headers):
    past = date.today() - timedelta(days=5)
    goal = _money_goal(client, auth_headers, deadline=str(past))
    assert goal["deadline_state"] == "deadline_passed"
    assert goal["required_monthly_saving_minor"] is None


def test_no_deadline_state(client, auth_headers):
    goal = _money_goal(client, auth_headers)
    assert goal["deadline_state"] == "no_deadline"
    assert goal["required_monthly_saving_minor"] is None


def test_completion_requires_criteria_or_confirmation(client, auth_headers):
    goal = _money_goal(client, auth_headers)
    # Not funded -> cannot complete without explicit confirmation.
    assert client.post(f"/api/goals/{goal['id']}/complete",
                       headers=auth_headers).status_code == 422
    # User explicitly confirms.
    completed = client.post(f"/api/goals/{goal['id']}/complete?force=true",
                            headers=auth_headers)
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    # Contributions to completed goals rejected.
    assert client.post(f"/api/goals/{goal['id']}/contributions",
                       json={"amount_minor": 100},
                       headers=auth_headers).status_code == 409


def test_validated_completion(client, auth_headers):
    goal = _money_goal(client, auth_headers, target_amount_minor=100000)
    client.post(f"/api/goals/{goal['id']}/contributions",
                json={"amount_minor": 100000}, headers=auth_headers)
    resp = client.post(f"/api/goals/{goal['id']}/complete", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["remaining_amount_minor"] == 0


def test_goal_validation_rules(client, auth_headers):
    assert client.post("/api/goals",
                       json={"name": "Bad", "type": "money"},
                       headers=auth_headers).status_code == 422
    assert client.post("/api/goals",
                       json={"name": "Bad", "type": "quantity"},
                       headers=auth_headers).status_code == 422


def test_goal_isolation_between_users(client, auth_headers, second_user_headers):
    goal = _money_goal(client, auth_headers)
    assert client.get(f"/api/goals/{goal['id']}",
                      headers=second_user_headers).status_code == 404
    assert client.post(f"/api/goals/{goal['id']}/contributions",
                       json={"amount_minor": 10},
                       headers=second_user_headers).status_code == 404
