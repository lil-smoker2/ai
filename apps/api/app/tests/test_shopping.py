"""Shopping list and purchase-workflow tests (spec 4.4, 5.2)."""
import pytest


@pytest.fixture()
def clothing_cat(client, auth_headers):
    cats = client.get("/api/inventory/categories", headers=auth_headers).json()
    return next(c for c in cats if c["name"] == "Clothing")


@pytest.fixture()
def cash_account(client, auth_headers):
    return client.post(
        "/api/accounts",
        json={"name": "Cash", "type": "cash"},
        headers=auth_headers,
    ).json()


@pytest.fixture()
def shopping_list(client, auth_headers):
    resp = client.post(
        "/api/shopping/lists", json={"name": "Market run"}, headers=auth_headers
    )
    assert resp.status_code == 201
    return resp.json()


def _make_item(client, auth_headers, clothing_cat, **overrides):
    body = {
        "name": "Trousers",
        "category_id": clothing_cat["id"],
        "quantity_owned": 5,
        "target_quantity": 20,
        "estimated_unit_cost_minor": 150000,
    } | overrides
    return client.post(
        "/api/inventory/items", json=body, headers=auth_headers
    ).json()


# --- Lists and lines ---

def test_list_crud(client, auth_headers, shopping_list):
    assert shopping_list["name"] == "Market run"
    fetched = client.get(
        f"/api/shopping/lists/{shopping_list['id']}", headers=auth_headers
    ).json()
    assert fetched["id"] == shopping_list["id"]

    updated = client.put(
        f"/api/shopping/lists/{shopping_list['id']}",
        json={"name": "Weekend market run"},
        headers=auth_headers,
    ).json()
    assert updated["name"] == "Weekend market run"

    page = client.get("/api/shopping/lists", headers=auth_headers).json()
    assert page["page"]["total"] == 1


def test_line_total_includes_delivery_transport_fees(
    client, auth_headers, shopping_list
):
    item = client.post(
        f"/api/shopping/lists/{shopping_list['id']}/items",
        json={
            "name": "Sufuria",
            "quantity_needed": 2,
            "estimated_unit_cost_minor": 250000,
            "delivery_cost_minor": 10000,
            "transport_cost_minor": 5000,
            "fees_minor": 1500,
        },
        headers=auth_headers,
    ).json()
    # 2 x 2500.00 + 100.00 + 50.00 + 15.00
    assert item["estimated_item_cost_minor"] == 500000
    assert item["estimated_total_minor"] == 516500
    assert item["price_needed"] is False


def test_line_without_price_shows_price_needed(
    client, auth_headers, shopping_list
):
    item = client.post(
        f"/api/shopping/lists/{shopping_list['id']}/items",
        json={"name": "Unknown gadget", "quantity_needed": 1},
        headers=auth_headers,
    ).json()
    assert item["estimated_total_minor"] is None
    assert item["price_needed"] is True


def test_generate_from_shortages_uses_saved_records(
    client, auth_headers, clothing_cat, shopping_list
):
    inv = _make_item(client, auth_headers, clothing_cat)  # shortage 15
    lines = client.post(
        f"/api/shopping/lists/{shopping_list['id']}/generate-from-shortages",
        headers=auth_headers,
    ).json()
    assert len(lines) == 1
    line = lines[0]
    assert line["name"] == "Trousers"
    assert line["quantity_needed"] == 15
    assert line["estimated_unit_cost_minor"] == 150000
    assert line["price_source"] == "estimate"  # never labelled verified
    assert line["inventory_item_id"] == inv["id"]
    assert line["estimated_total_minor"] == 15 * 150000

    # Re-running does not duplicate lines for the same shortage.
    again = client.post(
        f"/api/shopping/lists/{shopping_list['id']}/generate-from-shortages",
        headers=auth_headers,
    ).json()
    assert again == []


def test_generate_respects_verified_prices(
    client, auth_headers, clothing_cat, shopping_list
):
    _make_item(
        client, auth_headers, clothing_cat,
        name="Jeans", price_verified=True, price_source="Gikomba market",
    )
    lines = client.post(
        f"/api/shopping/lists/{shopping_list['id']}/generate-from-shortages",
        headers=auth_headers,
    ).json()
    assert lines[0]["price_source"] == "verified"


# --- Purchase workflow ---

def _purchase_line(client, auth_headers, shopping_list, name="Socks",
                   unit_minor=10000, qty=3, inventory=True, clothing=None):
    inv = None
    if inventory:
        inv = _make_item(
            client, auth_headers, clothing,
            name=name, quantity_owned=0, target_quantity=qty,
            estimated_unit_cost_minor=unit_minor,
        )
    line = client.post(
        f"/api/shopping/lists/{shopping_list['id']}/items",
        json={
            "name": name,
            "quantity_needed": qty,
            "estimated_unit_cost_minor": unit_minor,
            "inventory_item_id": inv["id"] if inv else None,
        },
        headers=auth_headers,
    ).json()
    return line


def _record(client, auth_headers, line, qty, amount, key, account=None, **kw):
    return client.post(
        f"/api/shopping/items/{line['id']}/purchase",
        json={
            "quantity": qty,
            "amount_paid_minor": amount,
            "account_id": account["id"] if account else None,
            "idempotency_key": key,
            **kw,
        },
        headers=auth_headers,
    )


def test_purchase_updates_every_record_once(
    client, auth_headers, clothing_cat, shopping_list, cash_account
):
    """Spec 5.2: one purchase updates transaction, inventory and goal once."""
    inv = _make_item(
        client, auth_headers, clothing_cat,
        name="Trousers", quantity_owned=5, target_quantity=20,
        estimated_unit_cost_minor=150000,
    )
    goal = client.post(
        "/api/goals",
        json={
            "name": "Wardrobe", "type": "quantity", "target_quantity": 20,
            "current_quantity": 5, "inventory_item_id": inv["id"],
        },
        headers=auth_headers,
    ).json()
    line = client.post(
        f"/api/shopping/lists/{shopping_list['id']}/items",
        json={"name": "Trousers", "quantity_needed": 15,
              "estimated_unit_cost_minor": 150000,
              "inventory_item_id": inv["id"], "goal_id": goal["id"]},
        headers=auth_headers,
    ).json()

    resp = _record(client, auth_headers, line, 5, 750000, "buy-trousers-1",
                   account=cash_account)
    assert resp.status_code == 201
    record = resp.json()
    assert record["added_inventory_quantity"] == 5
    assert record["transaction_id"] is not None

    # Inventory updated exactly once.
    inv_after = client.get(
        f"/api/inventory/items/{inv['id']}", headers=auth_headers
    ).json()
    assert inv_after["quantity_owned"] == 10
    # Goal progress updated exactly once.
    goal_after = client.get(f"/api/goals/{goal['id']}", headers=auth_headers).json()
    assert goal_after["current_quantity"] == 10
    # Expense transaction exists against the funding account.
    txn = client.get(
        f"/api/transactions/{record['transaction_id']}", headers=auth_headers
    ).json()
    assert txn["type"] == "expense"
    assert txn["amount_minor"] == 750000
    assert txn["from_account_id"] == cash_account["id"]
    # Line marked purchased.
    line_after = client.get(
        f"/api/shopping/items/{line['id']}", headers=auth_headers
    ).json()
    assert line_after["status"] == "purchased"


def test_repeated_purchase_request_is_idempotent(
    client, auth_headers, clothing_cat, shopping_list, cash_account
):
    line = _purchase_line(client, auth_headers, shopping_list,
                          clothing=clothing_cat)  # qty 3 @ 100.00
    first = _record(client, auth_headers, line, 3, 30000, "socks-key-001",
                    account=cash_account)
    replay = _record(client, auth_headers, line, 3, 30000, "socks-key-001",
                     account=cash_account)
    assert first.json()["id"] == replay.json()["id"]

    # Exactly one purchase, one transaction, one quantity event.
    purchases = client.get(
        f"/api/shopping/items/{line['id']}/purchases", headers=auth_headers
    ).json()
    assert len(purchases) == 1
    txns = client.get("/api/transactions", headers=auth_headers).json()
    assert txns["page"]["total"] == 1
    inv_id = line["inventory_item_id"]
    history = client.get(
        f"/api/inventory/items/{inv_id}/history", headers=auth_headers
    ).json()
    assert len([e for e in history if e["reason"] == "purchase"]) == 1
    item = client.get(f"/api/inventory/items/{inv_id}", headers=auth_headers).json()
    assert item["quantity_owned"] == 3


def test_second_purchase_after_replay_needs_new_line_state(
    client, auth_headers, clothing_cat, shopping_list
):
    line = _purchase_line(client, auth_headers, shopping_list,
                          clothing=clothing_cat)
    _record(client, auth_headers, line, 3, 30000, "socks-key-002")
    # Purchased lines reject further purchases (prevents silent double-buys).
    resp = _record(client, auth_headers, line, 3, 30000, "socks-key-003")
    assert resp.status_code == 409


def test_purchase_without_account_is_unallocated(client, auth_headers,
                                                 shopping_list):
    line = _purchase_line(client, auth_headers, shopping_list, inventory=False)
    record = _record(client, auth_headers, line, 1, 5000, "no-account-key").json()
    txn = client.get(
        f"/api/transactions/{record['transaction_id']}", headers=auth_headers
    ).json()
    assert txn["from_account_id"] is None


def test_purchase_add_to_inventory_false_leaves_quantity(
    client, auth_headers, clothing_cat, shopping_list
):
    line = _purchase_line(client, auth_headers, shopping_list,
                          clothing=clothing_cat)
    _record(client, auth_headers, line, 3, 30000, "keep-qty-key",
            add_to_inventory=False)
    item = client.get(
        f"/api/inventory/items/{line['inventory_item_id']}", headers=auth_headers
    ).json()
    assert item["quantity_owned"] == 0


# --- Authorization and isolation ---

def test_requires_auth(client, shopping_list):
    assert client.get("/api/shopping/lists").status_code == 401


def test_second_user_cannot_touch_lists(client, auth_headers, shopping_list,
                                        second_user_headers):
    assert client.get(
        f"/api/shopping/lists/{shopping_list['id']}",
        headers=second_user_headers,
    ).status_code == 404
    line = client.post(
        f"/api/shopping/lists/{shopping_list['id']}/items",
        json={"name": "X", "quantity_needed": 1}, headers=auth_headers,
    ).json()
    assert client.post(
        f"/api/shopping/items/{line['id']}/purchase",
        json={"quantity": 1, "amount_paid_minor": 100,
              "idempotency_key": "intruder-key-1"},
        headers=second_user_headers,
    ).status_code == 404


def test_cannot_link_another_users_inventory_item(
    client, auth_headers, shopping_list, second_user_headers
):
    other_inv = client.post(
        "/api/inventory/categories", json={"name": "Custom"},
        headers=second_user_headers,
    )
    other_cat = other_inv.json()
    item = client.post(
        "/api/inventory/items",
        json={"name": "Hidden", "category_id": other_cat["id"]},
        headers=second_user_headers,
    ).json()
    resp = client.post(
        f"/api/shopping/lists/{shopping_list['id']}/items",
        json={"name": "Copy", "quantity_needed": 1, "inventory_item_id": item["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_delete_list_requires_confirm(client, auth_headers, shopping_list):
    resp = client.delete(
        f"/api/shopping/lists/{shopping_list['id']}", headers=auth_headers
    )
    assert resp.status_code == 400
    assert client.delete(
        f"/api/shopping/lists/{shopping_list['id']}?confirm=true",
        headers=auth_headers,
    ).status_code == 204
    assert client.get(
        f"/api/shopping/lists/{shopping_list['id']}", headers=auth_headers
    ).status_code == 404
