"""Inventory calculations and workflow tests."""
import pytest


@pytest.fixture()
def clothing_cat(client, auth_headers):
    cats = client.get("/api/inventory/categories", headers=auth_headers).json()
    return next(c for c in cats if c["name"] == "Clothing")


def test_default_categories_seeded(client, auth_headers):
    names = [c["name"] for c in
             client.get("/api/inventory/categories", headers=auth_headers).json()]
    assert "Clothing" in names and "Household" in names


def test_shortage_and_cost_trousers_example(client, auth_headers, clothing_cat):
    """Spec journey: 5 trousers owned, target 20, unit price 1500 KES."""
    item = client.post(
        "/api/inventory/items",
        json={
            "name": "Trousers",
            "category_id": clothing_cat["id"],
            "quantity_owned": 5,
            "target_quantity": 20,
            "estimated_unit_cost_minor": 150000,
        },
        headers=auth_headers,
    ).json()
    assert item["shortage"] == 15
    assert item["estimated_cost_to_target_minor"] == 15 * 150000
    assert item["price_needed"] is False


def test_missing_price_shows_price_needed_not_zero(client, auth_headers, clothing_cat):
    item = client.post(
        "/api/inventory/items",
        json={"name": "Jeans", "category_id": clothing_cat["id"],
              "quantity_owned": 1, "target_quantity": 4},
        headers=auth_headers,
    ).json()
    assert item["shortage"] == 3
    assert item["estimated_cost_to_target_minor"] is None
    assert item["price_needed"] is True


def test_no_shortage_when_over_target(client, auth_headers, clothing_cat):
    item = client.post(
        "/api/inventory/items",
        json={"name": "Socks", "category_id": clothing_cat["id"],
              "quantity_owned": 10, "target_quantity": 8,
              "estimated_unit_cost_minor": 10000},
        headers=auth_headers,
    ).json()
    assert item["shortage"] == 0
    assert item["estimated_cost_to_target_minor"] == 0


def test_quantity_adjustment_and_history(client, auth_headers, clothing_cat):
    item = client.post(
        "/api/inventory/items",
        json={"name": "Shirts", "category_id": clothing_cat["id"],
              "quantity_owned": 2},
        headers=auth_headers,
    )
    item_id = item.json()["id"]
    updated = client.post(
        f"/api/inventory/items/{item_id}/adjust-quantity",
        json={"change": 3, "reason": "purchase"},
        headers=auth_headers,
    ).json()
    assert updated["quantity_owned"] == 5

    history = client.get(
        f"/api/inventory/items/{item_id}/history", headers=auth_headers
    ).json()
    assert {e["change"] for e in history} == {2, 3}


def test_quantity_cannot_go_negative(client, auth_headers, clothing_cat):
    item = client.post(
        "/api/inventory/items",
        json={"name": "Belt", "category_id": clothing_cat["id"], "quantity_owned": 1},
        headers=auth_headers,
    ).json()
    resp = client.post(
        f"/api/inventory/items/{item['id']}/adjust-quantity",
        json={"change": -5},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_soft_delete_preserves_history(client, auth_headers, clothing_cat):
    item = client.post(
        "/api/inventory/items",
        json={"name": "Jacket", "category_id": clothing_cat["id"], "quantity_owned": 1},
        headers=auth_headers,
    ).json()
    # Deletion without confirmation is rejected.
    assert client.delete(
        f"/api/inventory/items/{item['id']}", headers=auth_headers
    ).status_code == 400

    assert client.delete(
        f"/api/inventory/items/{item['id']}?confirm=true", headers=auth_headers
    ).status_code == 204
    assert client.get(
        f"/api/inventory/items/{item['id']}", headers=auth_headers
    ).status_code == 404
    # History is still retrievable (records preserved).
    assert len(client.get(
        f"/api/inventory/items/{item['id']}/history", headers=auth_headers
    ).json()) == 1


def test_category_validation(client, auth_headers):
    assert client.post(
        "/api/inventory/items",
        json={"name": "Ghost", "category_id": 999999},
        headers=auth_headers,
    ).status_code == 404
