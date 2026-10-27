"""Savings & Earnings tests: income normalization, business profit, forecast."""
from datetime import date


def _today() -> date:
    return date.today()


# --- Income sources ---

def test_create_income_source_and_monthly_normalization(client, auth_headers):
    src = client.post(
        "/api/earnings/income-sources",
        json={"name": "Salary", "expected_amount_minor": 4500000,
              "frequency": "monthly"},
        headers=auth_headers,
    ).json()
    assert src["monthly_expected_minor"] == 4500000

    yearly = client.post(
        "/api/earnings/income-sources",
        json={"name": "Bonus", "expected_amount_minor": 12000000,
              "frequency": "yearly"},
        headers=auth_headers,
    ).json()
    # KES 120,000.00 / 12 = KES 10,000.00 per month (1,000,000 minor)
    assert yearly["monthly_expected_minor"] == 1000000

    once = client.post(
        "/api/earnings/income-sources",
        json={"name": "Gift", "expected_amount_minor": 500000, "frequency": "once"},
        headers=auth_headers,
    ).json()
    # One-time money is not a recurring run-rate.
    assert once["monthly_expected_minor"] == 0


def test_update_and_deactivate_income_source(client, auth_headers):
    src = client.post(
        "/api/earnings/income-sources",
        json={"name": "Freelance", "expected_amount_minor": 1000000,
              "frequency": "weekly"},
        headers=auth_headers,
    ).json()
    updated = client.put(
        f"/api/earnings/income-sources/{src['id']}",
        json={"active": False},
        headers=auth_headers,
    ).json()
    assert updated["active"] is False


def test_weekly_normalization_rounds(client, auth_headers):
    src = client.post(
        "/api/earnings/income-sources",
        json={"name": "Hustle", "expected_amount_minor": 100000, "frequency": "weekly"},
        headers=auth_headers,
    ).json()
    # 1000.00 x (30.44 / 7) ~ 4.348 -> 434,857 minor
    assert src["monthly_expected_minor"] == 434857


# --- Business records ---

def test_business_net_profit_per_business(client, auth_headers):
    for amount, kind in [(500000, "revenue"), (200000, "revenue"), (150000, "expense")]:
        client.post(
            "/api/earnings/business",
            json={"business_name": "Boda", "type": kind,
                  "amount_minor": amount, "occurred_on": _today().isoformat()},
            headers=auth_headers,
        )
    profits = client.get(
        "/api/earnings/business/profit", headers=auth_headers
    ).json()
    assert len(profits) == 1
    assert profits[0]["revenue_minor"] == 700000
    assert profits[0]["expenses_minor"] == 150000
    assert profits[0]["net_profit_minor"] == 550000


def test_business_records_exclude_other_months(client, auth_headers):
    client.post(
        "/api/earnings/business",
        json={"business_name": "Shop", "type": "revenue", "amount_minor": 300000,
              "occurred_on": "2020-01-05"},
        headers=auth_headers,
    )
    summary = client.get("/api/earnings/summary", headers=auth_headers).json()
    # This month only: the 2020 record is excluded.
    assert summary["business_revenue_this_month_minor"] == 0


# --- Forecast ---

def test_forecast_combines_records_with_expected_income(
    client, auth_headers
):
    # Confirmed starting balance of 10,000.00.
    account = client.post(
        "/api/accounts", json={"name": "Cash", "type": "cash"},
        headers=auth_headers,
    ).json()
    client.post(
        f"/api/accounts/{account['id']}/initialize",
        json={"balance_minor": 1000000}, headers=auth_headers,
    )
    # Expected monthly income of 45,000.00.
    client.post(
        "/api/earnings/income-sources",
        json={"name": "Salary", "expected_amount_minor": 4500000,
              "frequency": "monthly", "reliability": "confirmed"},
        headers=auth_headers,
    )
    # A money goal short by 5,000.00 (obligation).
    goal = client.post(
        "/api/goals",
        json={"name": "Emergency", "type": "money", "target_amount_minor": 500000},
        headers=auth_headers,
    ).json()

    summary = client.get("/api/earnings/summary", headers=auth_headers).json()
    assert summary["recorded_available_balance_minor"] == 1000000
    assert summary["monthly_expected_income_minor"] == 4500000
    assert summary["outstanding_obligations_minor"] == 500000
    # 10,000 + 45,000 expected - 5,000 outstanding = 50,000.00
    assert summary["available_for_planning_minor"] == 5000000
    assert summary["assumptions"]  # forecast states its assumptions


def test_forecast_is_unknown_without_initialized_balance(client, auth_headers):
    client.post(
        "/api/earnings/income-sources",
        json={"name": "Salary", "expected_amount_minor": 4500000,
              "frequency": "monthly"},
        headers=auth_headers,
    )
    summary = client.get("/api/earnings/summary", headers=auth_headers).json()
    # Never a fake zero: with no initialized account the plan value is null.
    assert summary["recorded_available_balance_minor"] is None
    assert summary["available_for_planning_minor"] is None


def test_inactive_income_excluded_from_forecast(client, auth_headers):
    src = client.post(
        "/api/earnings/income-sources",
        json={"name": "Gig", "expected_amount_minor": 2000000, "frequency": "monthly"},
        headers=auth_headers,
    ).json()
    client.put(
        f"/api/earnings/income-sources/{src['id']}",
        json={"active": False}, headers=auth_headers,
    )
    summary = client.get("/api/earnings/summary", headers=auth_headers).json()
    assert summary["monthly_expected_income_minor"] == 0


# --- Authorization and isolation ---

def test_requires_auth(client):
    assert client.get("/api/earnings/income-sources").status_code == 401
    assert client.get("/api/earnings/summary").status_code == 401


def test_cannot_touch_another_users_income_source(
    client, auth_headers, second_user_headers
):
    src = client.post(
        "/api/earnings/income-sources",
        json={"name": "Mine", "expected_amount_minor": 100000,
              "frequency": "monthly"},
        headers=auth_headers,
    ).json()
    assert client.put(
        f"/api/earnings/income-sources/{src['id']}",
        json={"active": False}, headers=second_user_headers,
    ).status_code == 404
    assert client.delete(
        f"/api/earnings/income-sources/{src['id']}", headers=second_user_headers
    ).status_code == 404
