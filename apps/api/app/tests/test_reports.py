"""Reports tests: every figure must reconcile with the underlying records,
transfers must never inflate income/expense, unknowns stay unknown, filters
narrow real rows, and the CSV export mirrors the ledger."""
from datetime import date, timedelta


def _account(client, headers, name="Cash", type_="cash", balance=0, **details):
    acct = client.post("/api/accounts", json={"name": name, "type": type_, **details},
                       headers=headers).json()
    client.post(f"/api/accounts/{acct['id']}/initialize",
                json={"balance_minor": balance}, headers=headers)
    return acct


def _txn(client, headers, **kwargs):
    kwargs.setdefault("occurred_on", str(date.today()))
    return client.post("/api/transactions", json=kwargs, headers=headers)


def _summary(client, headers, **params):
    resp = client.get("/api/reports/summary", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_reports_require_auth(client):
    assert client.get("/api/reports/summary").status_code == 401
    assert client.get("/api/reports/export.csv").status_code == 401


def test_empty_report_is_honest(client, auth_headers):
    r = _summary(client, auth_headers)
    assert r["cash_flow"]["income_minor"] == 0
    assert r["cash_flow"]["net_minor"] == 0
    # No initialized account -> balance history is unknown, not a fake zero.
    assert r["balance_history"]["available"] is False
    assert r["shortage"]["estimated_cost_minor"] == 0  # genuinely nothing below target


def test_cash_flow_and_category_reconcile(client, auth_headers):
    acct = _account(client, auth_headers, balance=100000)
    _txn(client, auth_headers, type="income", amount_minor=50000,
         account_id=acct["id"], category="allowance")
    _txn(client, auth_headers, type="expense", amount_minor=12000,
         account_id=acct["id"], category="food")
    _txn(client, auth_headers, type="expense", amount_minor=8000,
         account_id=acct["id"], category="food")

    r = _summary(client, auth_headers)
    assert r["cash_flow"]["income_minor"] == 50000
    assert r["cash_flow"]["expense_minor"] == 20000
    assert r["cash_flow"]["net_minor"] == 30000
    food = next(c for c in r["spending_by_category"] if c["category"] == "Food")
    assert food["total_minor"] == 20000 and food["count"] == 2


def test_transfers_never_count_as_income_or_expense(client, auth_headers):
    cash = _account(client, auth_headers, "Cash", balance=100000)
    mpesa = _account(client, auth_headers, "M-PESA", "mpesa", balance=100000,
                     mpesa_number="0712345678")
    _txn(client, auth_headers, type="transfer", amount_minor=30000,
         from_account_id=cash["id"], to_account_id=mpesa["id"])

    r = _summary(client, auth_headers)
    assert r["cash_flow"]["income_minor"] == 0
    assert r["cash_flow"]["expense_minor"] == 0
    assert r["cash_flow"]["transfers_minor"] == 30000
    # Net worth is unchanged by an internal transfer.
    last = r["balance_history"]["points"][-1]
    assert last["running_balance_minor"] == 200000
    assert last["net_change_minor"] == 0


def test_balance_history_running_balance(client, auth_headers):
    acct = _account(client, auth_headers, balance=100000)
    _txn(client, auth_headers, type="income", amount_minor=20000, account_id=acct["id"])
    _txn(client, auth_headers, type="expense", amount_minor=5000, account_id=acct["id"])

    bh = _summary(client, auth_headers)["balance_history"]
    assert bh["starting_balance_minor"] == 100000
    assert bh["points"][-1]["net_change_minor"] == 15000
    assert bh["points"][-1]["running_balance_minor"] == 115000


def test_date_and_category_filters(client, auth_headers):
    acct = _account(client, auth_headers, balance=0)
    past = str(date.today() - timedelta(days=400))
    _txn(client, auth_headers, type="expense", amount_minor=999999,
         account_id=acct["id"], category="old", occurred_on=past)
    _txn(client, auth_headers, type="expense", amount_minor=4000,
         account_id=acct["id"], category="food")

    filtered = _summary(client, auth_headers, category="food")
    assert filtered["cash_flow"]["expense_minor"] == 4000

    windowed = _summary(client, auth_headers, date_from=str(date.today().replace(day=1)))
    assert windowed["cash_flow"]["expense_minor"] == 4000


def test_account_filter_scopes_balance_and_flow(client, auth_headers):
    cash = _account(client, auth_headers, "Cash", balance=10000)
    bank = _account(client, auth_headers, "Bank", "bank", balance=500000,
                    bank_name="Equity Bank", account_number="0110045678")
    _txn(client, auth_headers, type="expense", amount_minor=6000, account_id=cash["id"])
    _txn(client, auth_headers, type="expense", amount_minor=70000, account_id=bank["id"])

    r = _summary(client, auth_headers, account_id=cash["id"])
    assert r["cash_flow"]["expense_minor"] == 6000
    assert r["balance_history"]["points"][-1]["running_balance_minor"] == 4000


def test_savings_and_goal_progress(client, auth_headers):
    goal = client.post("/api/goals", json={"name": "Laptop", "type": "money",
                       "target_amount_minor": 100000}, headers=auth_headers).json()
    client.post(f"/api/goals/{goal['id']}/contributions",
                json={"amount_minor": 30000}, headers=auth_headers)

    r = _summary(client, auth_headers)
    assert r["savings"]["total_saved_in_goals_minor"] == 30000
    assert r["savings"]["active_goals"] == 1
    laptop = next(g for g in r["goals"] if g["name"] == "Laptop")
    assert laptop["percent"] == 30
    assert laptop["remaining_amount_minor"] == 70000


def test_shortage_price_unknown_is_not_a_number(client, auth_headers):
    cats = client.get("/api/inventory/categories", headers=auth_headers).json()
    cat = next(c for c in cats if c["name"].lower() == "clothing")
    client.post("/api/inventory/items", json={"name": "Chinos", "category_id": cat["id"],
                "quantity_owned": 1, "target_quantity": 3,
                "estimated_unit_cost_minor": None}, headers=auth_headers)

    s = _summary(client, auth_headers)["shortage"]
    assert s["items_below_target"] == 1
    assert s["price_needed_items"] == 1
    assert s["estimated_cost_minor"] is None  # not fabricated


def test_business_profit(client, auth_headers):
    client.post("/api/earnings/business", json={"business_name": "Side hustle",
                "type": "revenue", "amount_minor": 50000}, headers=auth_headers)
    client.post("/api/earnings/business", json={"business_name": "Side hustle",
                "type": "expense", "amount_minor": 20000}, headers=auth_headers)
    b = _summary(client, auth_headers)["business"]
    assert b == {"revenue_minor": 50000, "expenses_minor": 20000,
                 "net_profit_minor": 30000}


def test_obligations_never_claim_paid(client, auth_headers):
    fee = client.post("/api/student/fees", json={"name": "Tuition",
                    "category": "tuition", "amount_due_minor": 100000,
                    "due_on": str(date.today() - timedelta(days=1))},
                    headers=auth_headers).json()
    client.post(f"/api/student/fees/{fee['id']}/payments",
                json={"amount_minor": 40000, "idempotency_key": "p1"}, headers=auth_headers)

    o = _summary(client, auth_headers)["obligations"]
    assert o["outstanding_fees_minor"] == 60000
    assert o["overdue_count"] >= 1
    tuition = next(i for i in o["items"] if i["name"] == "Tuition")
    assert tuition["status"] == "overdue" and tuition["outstanding_minor"] == 60000


def test_csv_export_mirrors_ledger(client, auth_headers):
    acct = _account(client, auth_headers, balance=100000)
    _txn(client, auth_headers, type="expense", amount_minor=4000,
         account_id=acct["id"], category="food", description="lunch")

    resp = client.get("/api/reports/export.csv", params={"category": "food"},
                      headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    lines = resp.text.strip().splitlines()
    assert lines[0] == "date,type,category,description,amount,currency"
    assert "lunch" in lines[1]
    assert "40.00" in lines[1]  # minor 4000 -> major 40.00, no float error
