"""Dashboard figures must derive from saved records, never invented values."""
from datetime import date


def test_empty_dashboard_has_unknown_balance_not_zero(client, auth_headers):
    body = client.get("/api/dashboard/summary", headers=auth_headers).json()
    assert body["total_available_minor"] is None
    assert body["income_this_month_minor"] == 0
    assert body["distinct_inventory_items"] == 0


def test_dashboard_reflects_records(client, auth_headers):
    cash = client.post("/api/accounts", json={"name": "Cash", "type": "cash"},
                       headers=auth_headers).json()
    client.post(f"/api/accounts/{cash['id']}/initialize",
                json={"balance_minor": 200000}, headers=auth_headers)
    client.post("/api/transactions",
                json={"type": "income", "amount_minor": 50000,
                      "account_id": cash["id"], "occurred_on": str(date.today())},
                headers=auth_headers)

    cats = client.get("/api/inventory/categories", headers=auth_headers).json()
    client.post("/api/inventory/items",
                json={"name": "Trousers", "category_id": cats[0]["id"],
                      "quantity_owned": 5, "target_quantity": 20,
                      "estimated_unit_cost_minor": 150000},
                headers=auth_headers)
    # A second item without a price: total shortage cost must become null.
    client.post("/api/inventory/items",
                json={"name": "Sufuria", "category_id": cats[1]["id"],
                      "quantity_owned": 1, "target_quantity": 5},
                headers=auth_headers)

    goal = client.post("/api/goals",
                       json={"name": "Fees", "type": "money",
                             "target_amount_minor": 1000000},
                       headers=auth_headers).json()
    client.post(f"/api/goals/{goal['id']}/contributions",
                json={"amount_minor": 200000,
                      "occurred_on": str(date.today())}, headers=auth_headers)

    body = client.get("/api/dashboard/summary", headers=auth_headers).json()
    assert body["total_available_minor"] == 250000
    assert body["income_this_month_minor"] == 50000
    assert body["savings_this_month_minor"] == 200000
    assert body["active_goals"] == 1
    assert body["outstanding_goal_amount_minor"] == 800000
    assert body["distinct_inventory_items"] == 2
    assert body["items_below_target"] == 2
    assert body["price_needed_items"] == 1
    assert body["estimated_shortage_cost_minor"] is None


def test_dashboard_shortage_cost_when_all_priced(client, auth_headers):
    cats = client.get("/api/inventory/categories", headers=auth_headers).json()
    client.post("/api/inventory/items",
                json={"name": "Trousers", "category_id": cats[0]["id"],
                      "quantity_owned": 5, "target_quantity": 20,
                      "estimated_unit_cost_minor": 150000},
                headers=auth_headers)
    body = client.get("/api/dashboard/summary", headers=auth_headers).json()
    assert body["estimated_shortage_cost_minor"] == 15 * 150000
