"""Finance tests: balances, transfers, idempotency, reversals."""
from datetime import date


def _account(client, headers, name="Cash", type_="cash", **details):
    return client.post(
        "/api/accounts", json={"name": name, "type": type_, **details},
        headers=headers,
    ).json()


def _txn(client, headers, **kwargs):
    kwargs.setdefault("occurred_on", str(date(2026, 10, 15)))
    return client.post("/api/transactions", json=kwargs, headers=headers)


def test_account_balance_unknown_until_initialized(client, auth_headers):
    acct = _account(client, auth_headers)
    assert acct["balance_minor"] is None
    assert acct["initialized"] is False

    summary = client.get("/api/accounts/summary", headers=auth_headers).json()
    assert summary["total_available_minor"] is None  # not faked as zero

    client.post(
        f"/api/accounts/{acct['id']}/initialize",
        json={"balance_minor": 1000000},  # 10,000.00 KES
        headers=auth_headers,
    )
    acct = client.get("/api/accounts", headers=auth_headers).json()[0]
    assert acct["balance_minor"] == 1000000


def test_income_expense_adjust_balance(client, auth_headers):
    acct = _account(client, auth_headers)
    client.post(f"/api/accounts/{acct['id']}/initialize",
                json={"balance_minor": 50000}, headers=auth_headers)

    _txn(client, auth_headers, type="income", amount_minor=20000,
         account_id=acct["id"], category="allowance")
    _txn(client, auth_headers, type="expense", amount_minor=7500,
         account_id=acct["id"], category="food")

    final = client.get("/api/accounts", headers=auth_headers).json()[0]
    assert final["balance_minor"] == 50000 + 20000 - 7500


def test_transfer_moves_funds_without_income_or_expense(client, auth_headers):
    cash = _account(client, auth_headers, "Cash")
    mpesa = _account(client, auth_headers, "M-PESA", "mpesa",
                     mpesa_number="0712 345 678")
    for a in (cash, mpesa):
        client.post(f"/api/accounts/{a['id']}/initialize",
                    json={"balance_minor": 100000}, headers=auth_headers)

    _txn(client, auth_headers, type="transfer", amount_minor=30000,
         from_account_id=cash["id"], to_account_id=mpesa["id"])

    accounts = {a["id"]: a for a in
                client.get("/api/accounts", headers=auth_headers).json()}
    assert accounts[cash["id"]]["balance_minor"] == 70000
    assert accounts[mpesa["id"]]["balance_minor"] == 130000

    month = client.get("/api/transactions/summary/month",
                       params={"month": "2026-10"},
                       headers=auth_headers).json()
    assert month["income_minor"] == 0
    assert month["expense_minor"] == 0
    assert month["transfers_minor"] == 30000


def test_transfer_to_same_account_rejected(client, auth_headers):
    cash = _account(client, auth_headers)
    resp = _txn(client, auth_headers, type="transfer", amount_minor=1000,
                from_account_id=cash["id"], to_account_id=cash["id"])
    assert resp.status_code == 422


def test_idempotent_transaction_creation(client, auth_headers):
    cash = _account(client, auth_headers)
    key = "purchase-001"
    first = _txn(client, auth_headers, type="expense", amount_minor=5000,
                 account_id=cash["id"], idempotency_key=key)
    second = _txn(client, auth_headers, type="expense", amount_minor=5000,
                  account_id=cash["id"], idempotency_key=key)
    assert first.json()["id"] == second.json()["id"]
    txns = client.get("/api/transactions", headers=auth_headers).json()
    assert txns["page"]["total"] == 1  # no duplicate write


def test_reversal_creates_compensating_record(client, auth_headers):
    cash = _account(client, auth_headers)
    client.post(f"/api/accounts/{cash['id']}/initialize",
                json={"balance_minor": 100000}, headers=auth_headers)
    expense = _txn(client, auth_headers, type="expense", amount_minor=25000,
                   account_id=cash["id"]).json()

    reversal = client.post(
        f"/api/transactions/{expense['id']}/reverse", headers=auth_headers
    ).json()
    assert reversal["to_account_id"] == cash["id"]
    assert reversal["reversal_of_id"] == expense["id"]

    acct = client.get("/api/accounts", headers=auth_headers).json()[0]
    assert acct["balance_minor"] == 100000  # fully compensated

    # Double reversal prevented.
    again = client.post(f"/api/transactions/{expense['id']}/reverse",
                        headers=auth_headers)
    assert again.status_code == 409


def test_negative_and_zero_amounts_rejected(client, auth_headers):
    cash = _account(client, auth_headers)
    assert _txn(client, auth_headers, type="expense", amount_minor=0,
                account_id=cash["id"]).status_code == 422
    assert _txn(client, auth_headers, type="expense", amount_minor=-100,
                account_id=cash["id"]).status_code == 422


def test_transaction_filters_and_pagination(client, auth_headers):
    cash = _account(client, auth_headers)
    for i in range(3):
        _txn(client, auth_headers, type="expense", amount_minor=1000 + i,
             account_id=cash["id"], category="food")
    _txn(client, auth_headers, type="income", amount_minor=9000,
         account_id=cash["id"], category="allowance")

    filtered = client.get("/api/transactions", params={"type": "expense"},
                          headers=auth_headers).json()
    assert filtered["page"]["total"] == 3
    assert filtered["page"]["page_size"] == 50
    page = client.get("/api/transactions", params={"page_size": 3, "page": 2},
                      headers=auth_headers).json()
    assert page["page"]["total"] == 4  # 3 expenses + 1 income
    assert len(page["transactions"]) == 1  # 4 records, 3 per page -> last page has 1


def test_cross_user_account_access_blocked(client, auth_headers, second_user_headers):
    mine = _account(client, auth_headers)
    resp = _txn(client, second_user_headers, type="income", amount_minor=100,
                account_id=mine["id"])
    assert resp.status_code == 404
