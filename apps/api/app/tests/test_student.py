"""Student Life tests: fee status math, idempotent payments, accommodation
availability (never auto-claimed), food budget derivation and isolation."""
from datetime import date, timedelta


def _fee(client, headers, **over):
    body = {"name": "Tuition", "amount_due_minor": 5000000, **over}
    return client.post("/api/student/fees", json=body, headers=headers).json()


# --- Fees ---

def test_new_fee_is_unpaid_with_full_outstanding(client, auth_headers):
    f = _fee(client, auth_headers)
    assert f["status"] == "unpaid"
    assert f["amount_paid_minor"] == 0
    assert f["outstanding_minor"] == 5000000


def test_record_payment_makes_partial_and_writes_transaction(client, auth_headers):
    f = _fee(client, auth_headers)
    pay = client.post(
        f"/api/student/fees/{f['id']}/payments",
        json={"amount_minor": 2000000, "idempotency_key": "k1"},
        headers=auth_headers,
    ).json()
    assert pay["transaction_id"] is not None

    fees = client.get("/api/student/fees", headers=auth_headers).json()
    updated = next(x for x in fees if x["id"] == f["id"])
    assert updated["status"] == "partial"
    assert updated["amount_paid_minor"] == 2000000
    assert updated["outstanding_minor"] == 3000000

    txns = client.get("/api/transactions", headers=auth_headers).json()["transactions"]
    assert any(t["category"] == "fees" and t["amount_minor"] == 2000000 for t in txns)


def test_full_payment_marks_fee_paid(client, auth_headers):
    f = _fee(client, auth_headers)
    client.post(
        f"/api/student/fees/{f['id']}/payments",
        json={"amount_minor": 5000000, "idempotency_key": "full"},
        headers=auth_headers,
    )
    got = client.get(f"/api/student/fees", headers=auth_headers).json()[0]
    assert got["status"] == "paid"
    assert got["outstanding_minor"] == 0


def test_payment_is_idempotent(client, auth_headers):
    f = _fee(client, auth_headers)
    body = {"amount_minor": 1500000, "idempotency_key": "same"}
    first = client.post(
        f"/api/student/fees/{f['id']}/payments", json=body, headers=auth_headers
    ).json()
    replay = client.post(
        f"/api/student/fees/{f['id']}/payments", json=body, headers=auth_headers
    ).json()
    assert replay["id"] == first["id"]

    got = client.get("/api/student/fees", headers=auth_headers).json()[0]
    # Paid once, not twice.
    assert got["amount_paid_minor"] == 1500000
    txns = client.get("/api/transactions", headers=auth_headers).json()["transactions"]
    assert len([t for t in txns if t["category"] == "fees"]) == 1


def test_fee_delete_requires_confirm(client, auth_headers):
    f = _fee(client, auth_headers)
    assert client.delete(f"/api/student/fees/{f['id']}", headers=auth_headers).status_code == 400
    ok = client.delete(
        f"/api/student/fees/{f['id']}", headers=auth_headers, params={"confirm": "true"}
    )
    assert ok.status_code == 204
    assert client.get("/api/student/fees", headers=auth_headers).json() == []


# --- Accommodation ---

def test_hostel_starts_unchecked_never_booked(client, auth_headers):
    h = client.post(
        "/api/student/hostels", json={"name": "Green Park"}, headers=auth_headers
    ).json()
    assert h["status"] == "unchecked"
    assert h["last_checked_at"] is None
    assert h["monthly_rent_minor"] is None  # unknown, not zero


def test_availability_update_records_check_time(client, auth_headers):
    h = client.post(
        "/api/student/hostels", json={"name": "Green Park"}, headers=auth_headers
    ).json()
    updated = client.post(
        f"/api/student/hostels/{h['id']}/availability",
        json={"status": "available"},
        headers=auth_headers,
    ).json()
    assert updated["status"] == "available"
    assert updated["last_checked_at"] is not None


# --- Food budget ---

def test_food_budget_defaults_null_and_derives_daily(client, auth_headers):
    fb = client.get("/api/student/food-budget", headers=auth_headers).json()
    assert fb["weekly_budget_minor"] is None
    assert fb["daily_estimate_minor"] is None

    updated = client.put(
        "/api/student/food-budget",
        json={"weekly_budget_minor": 350000},
        headers=auth_headers,
    ).json()
    # 3,500.00 / 7 = 500.00 per day
    assert updated["daily_estimate_minor"] == 50000


# --- Summary ---

def test_summary_totals_and_overdue_count(client, auth_headers):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _fee(client, auth_headers, amount_due_minor=5000000, due_on=yesterday)
    _fee(client, auth_headers, name="Reg", amount_due_minor=1000000)
    s = client.get("/api/student/summary", headers=auth_headers).json()
    assert s["total_fees_due_minor"] == 6000000
    assert s["total_fees_outstanding_minor"] == 6000000
    assert s["overdue_fees_count"] == 1


# --- Isolation & auth ---

def test_cannot_link_another_users_goal_to_fee(client, auth_headers, second_user_headers):
    goal = client.post(
        "/api/goals",
        json={"name": "Their goal", "type": "money", "target_amount_minor": 100000},
        headers=second_user_headers,
    ).json()
    resp = client.post(
        "/api/student/fees",
        json={"name": "Fee", "amount_due_minor": 1000, "goal_id": goal["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_cross_user_fee_isolation(client, auth_headers, second_user_headers):
    f = _fee(client, auth_headers)
    resp = client.put(
        f"/api/student/fees/{f['id']}", json={"name": "x"}, headers=second_user_headers
    )
    assert resp.status_code == 404


def test_requires_auth(client):
    assert client.get("/api/student/fees").status_code == 401
