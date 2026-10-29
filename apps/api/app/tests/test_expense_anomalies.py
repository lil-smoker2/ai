"""Expense anomaly detection: a flag only where a category has a real middle.

The test is median/MAD over the user's own expenses per category inside a
90-day window, at the classical 3.5 modified z-score. What matters most here
is silence: thin categories, non-expense money movement, reversals, stale
spending and histories with no spread report nothing at all. Where a flag does
rise, the arithmetic is checked on round amounts so the median and the score
are exact.
"""
from datetime import date, timedelta

WINDOW = 90  # mirrors anomalies.LOOKBACK_DAYS
MIN_COUNT = 5  # mirrors anomalies.MIN_CATEGORY_EXPENSES


def _account(client, headers):
    resp = client.post("/api/accounts",
                       json={"name": "Cash", "type": "cash", "balance_minor": 10000000},
                       headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _spend(client, headers, account_id, amount_minor, category="Food",
           days_ago=1, **over):
    body = {
        "type": "expense", "amount_minor": amount_minor, "account_id": account_id,
        "category": category,
        "occurred_on": (date.today() - timedelta(days=days_ago)).isoformat(),
        **over,
    }
    resp = client.post("/api/transactions", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _anomalies(client, headers):
    resp = client.get("/api/transactions/anomalies", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _typical_day(client, headers, account_id, category="Food"):
    """One full, spread-free week of the same lunch - no middle to beat."""
    for i in range(MIN_COUNT):
        _spend(client, headers, account_id, 10000, category=category, days_ago=i + 1)


# --- silence: no dependable middle, no verdict -------------------------------

def test_a_fresh_account_reports_nothing(client, auth_headers):
    body = _anomalies(client, auth_headers)
    assert body["anomalies"] == []
    assert body["window_days"] == WINDOW
    assert body["min_category_expenses"] == MIN_COUNT


def test_a_thin_category_is_never_flagged_however_big(client, auth_headers):
    account = _account(client, auth_headers)
    for i in range(MIN_COUNT - 1):
        _spend(client, auth_headers, account, 10000, days_ago=i + 1)
    # A 50x amount, but four knowns do not make a "usual".
    _spend(client, auth_headers, account, 500000, days_ago=0)
    assert _anomalies(client, auth_headers)["anomalies"] == []


def test_identical_spending_has_no_spread_to_measure(client, auth_headers):
    account = _account(client, auth_headers)
    _typical_day(client, auth_headers, account)
    # MAD is zero: no amount deviates from the middle, so nothing is flagged.
    assert _anomalies(client, auth_headers)["anomalies"] == []


def test_spending_outside_the_window_is_not_compared(client, auth_headers):
    account = _account(client, auth_headers)
    _typical_day(client, auth_headers, account)
    # A big old expense sits outside the window entirely; nothing is claimed
    # about spending this app can no longer see a recent pattern in.
    _spend(client, auth_headers, account, 900000, days_ago=WINDOW + 10)
    assert _anomalies(client, auth_headers)["anomalies"] == []


def test_income_and_transfers_are_not_spending(client, auth_headers):
    account = _account(client, auth_headers)
    other = client.post("/api/accounts",
                        json={"name": "Bank", "type": "bank",
                              "bank_name": "Equity Bank",
                              "account_number": "011004567890",
                              "balance_minor": 10000000},
                        headers=auth_headers).json()["id"]
    _typical_day(client, auth_headers, account)
    client.post("/api/transactions",
                json={"type": "income", "amount_minor": 900000, "account_id": account,
                      "occurred_on": date.today().isoformat()},
                headers=auth_headers)
    client.post("/api/transactions",
                json={"type": "transfer", "amount_minor": 900000,
                      "from_account_id": account, "to_account_id": other,
                      "occurred_on": date.today().isoformat()},
                headers=auth_headers)
    assert _anomalies(client, auth_headers)["anomalies"] == []


def test_a_reversed_expense_withdraws_its_claim(client, auth_headers):
    account = _account(client, auth_headers)
    _typical_day(client, auth_headers, account)
    big = _spend(client, auth_headers, account, 200000, days_ago=0)
    assert len(_anomalies(client, auth_headers)["anomalies"]) == 1
    # Correcting the record takes the outlier out of the population too.
    client.post(f"/api/transactions/{big['id']}/reverse", headers=auth_headers)
    assert _anomalies(client, auth_headers)["anomalies"] == []


# --- a real flag, stated as the comparison it came from -----------------------

def test_one_big_expense_against_a_spread_history_is_flagged(client, auth_headers):
    account = _account(client, auth_headers)
    _typical_day(client, auth_headers, account)                 # five at 10000
    _spend(client, auth_headers, account, 15000, days_ago=6)    # one small deviation
    _spend(client, auth_headers, account, 200000, days_ago=0)   # the outlier
    # median 10000, MAD 1000 -> z = 0.6745 * 190000 / 1000
    a = _anomalies(client, auth_headers)["anomalies"][0]
    assert a["amount_minor"] == 200000
    assert a["category_median_minor"] == 10000
    assert a["deviation_score"] == 128.16
    assert a["occurred_on"] == date.today().isoformat()
    assert isinstance(a["amount_minor"], int)


def test_categories_are_merged_regardless_of_spelling(client, auth_headers):
    account = _account(client, auth_headers)
    _spend(client, auth_headers, account, 10000, category="Transport", days_ago=1)
    _spend(client, auth_headers, account, 10000, category="transport", days_ago=2)
    _spend(client, auth_headers, account, 10000, category="TRANSPORT", days_ago=3)
    _spend(client, auth_headers, account, 15000, category="Transport", days_ago=4)
    _spend(client, auth_headers, account, 10000, category=" Transport ", days_ago=5)
    _spend(client, auth_headers, account, 200000, category="transport", days_ago=0)
    body = _anomalies(client, auth_headers)["anomalies"]
    # One category, one flag - and it is not split into thin sub-groups.
    assert len(body) == 1
    assert body[0]["category"] == "Transport"
