"""Net worth: derived from inventory records and saved without being typed in.

These cover the arithmetic the Net Worth page shows (what I have, what I still
need, what one costs, what it all comes to), the honesty rule that an unknown
price keeps the total unknown, the automatic saving of the figure, and the
picture each row carries.
"""
from datetime import date

from PIL import Image


def _make_image(path, fmt="JPEG", size=(160, 120), color=(90, 90, 120)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, fmt)
    return path


def _category(client, headers, name):
    resp = client.post("/api/inventory/categories", json={"name": name},
                       headers=headers)
    assert resp.status_code in (201, 409)
    cats = client.get("/api/inventory/categories", headers=headers).json()
    return next(c["id"] for c in cats if c["name"] == name)


def _item(client, headers, name, category_id, **fields):
    body = {"name": name, "category_id": category_id, **fields}
    resp = client.post("/api/inventory/items", json=body, headers=headers)
    assert resp.status_code == 201
    return resp.json()


def test_net_worth_prices_what_is_held_and_what_is_still_needed(client, auth_headers):
    trousers = _category(client, auth_headers, "Trousers")
    _item(client, auth_headers, "Trousers", trousers,
          quantity_owned=2, target_quantity=4, estimated_unit_cost_minor=150000)

    body = client.get("/api/networth", headers=auth_headers).json()
    line = body["lines"][0]
    assert line["quantity_owned"] == 2
    assert line["needed_quantity"] == 2          # how much I may need
    assert line["unit_cost_minor"] == 150000     # how much one costs
    assert line["value_minor"] == 300000         # what mine is worth
    assert line["to_target_minor"] == 300000     # what is still missing
    assert line["price_needed"] is False

    assert body["net_worth_minor"] == 300000
    assert body["to_target_minor"] == 300000
    # "Total money I should have": the value I hold plus the shortfall.
    assert body["replacement_total_minor"] == 600000
    assert body["unpriced_items"] == 0
    assert body["saved"]["complete"] is True


def test_unpriced_owned_item_keeps_net_worth_unknown(client, auth_headers):
    hood = _category(client, auth_headers, "Clothing")
    _item(client, auth_headers, "Hoodie", hood,
          quantity_owned=2, estimated_unit_cost_minor=100000)
    _item(client, auth_headers, "Socks", hood, quantity_owned=3)

    body = client.get("/api/networth", headers=auth_headers).json()
    # The unpriced pair is not assumed free: the total stays unknown.
    assert body["net_worth_minor"] is None
    assert body["unpriced_items"] == 1
    assert body["valued_items"] == 1
    # ...while the part that is known is still reported honestly.
    assert body["priced_value_minor"] == 200000

    socks = next(l for l in body["lines"] if l["name"] == "Socks")
    assert socks["value_minor"] is None
    assert socks["price_needed"] is True
    assert body["saved"]["net_worth_minor"] is None
    assert body["saved"]["complete"] is False


def test_owning_nothing_yet_prices_nothing_never_blocks_a_total(client, auth_headers):
    pots = _category(client, auth_headers, "Household")
    _item(client, auth_headers, "Sufuria", pots, quantity_owned=0, target_quantity=3)

    body = client.get("/api/networth", headers=auth_headers).json()
    # Nothing owned contributes nothing, priced or not - so the worth itself is
    # known (zero) and no owned item is counted as unpriced.
    assert body["net_worth_minor"] == 0
    assert body["unpriced_items"] == 0
    # The cost of the shortfall, however, is still unknown.
    assert body["to_target_minor"] is None
    assert body["replacement_total_minor"] is None
    line = body["lines"][0]
    assert line["value_minor"] == 0
    assert line["to_target_minor"] is None
    assert line["price_needed"] is True  # the row still asks for a price


def test_net_worth_is_saved_and_refreshed_without_being_asked(client, auth_headers):
    cats = _category(client, auth_headers, "Electronics")
    item = _item(client, auth_headers, "Laptop", cats, quantity_owned=1,
                 estimated_unit_cost_minor=5000000)

    first = client.get("/api/networth", headers=auth_headers).json()["saved"]
    assert first["on_date"] == str(date.today())
    assert first["net_worth_minor"] == 5000000

    client.put(f"/api/inventory/items/{item['id']}",
               json={"estimated_unit_cost_minor": 4200000}, headers=auth_headers)

    body = client.get("/api/networth", headers=auth_headers).json()
    assert body["saved"]["net_worth_minor"] == 4200000
    # One row per day: the day's edits collapse into its final value.
    assert len(body["history"]) == 1

    # Quantity changes re-record too, not just prices.
    client.post(f"/api/inventory/items/{item['id']}/adjust-quantity",
                json={"change": 1, "reason": "purchase"}, headers=auth_headers)
    after = client.get("/api/networth", headers=auth_headers).json()
    assert after["saved"]["net_worth_minor"] == 8400000
    assert len(after["history"]) == 1


def test_deleting_an_item_takes_its_value_back_out(client, auth_headers):
    cats = _category(client, auth_headers, "Food")
    item = _item(client, auth_headers, "Maize flour", cats, quantity_owned=4,
                 estimated_unit_cost_minor=20000)
    assert client.get("/api/networth", headers=auth_headers).json()[
        "net_worth_minor"] == 80000

    client.delete(f"/api/inventory/items/{item['id']}?confirm=true",
                  headers=auth_headers)

    body = client.get("/api/networth", headers=auth_headers).json()
    assert body["items"] == 0
    assert body["net_worth_minor"] == 0


def test_a_row_carries_the_picture_from_its_category_folder(client, auth_headers,
                                                            assets_root):
    """A "Trousers" item shows the photo filed under clothing/trousers, chosen
    by the same matcher the gallery uses - no filename is wired in anywhere."""
    _make_image(assets_root / "clothing" / "trousers" / "chino.jpg")
    client.post("/api/assets/scan", json={}, headers=auth_headers)

    trousers = _category(client, auth_headers, "Trousers")
    _item(client, auth_headers, "Chino trousers", trousers, quantity_owned=1,
          estimated_unit_cost_minor=150000)

    line = client.get("/api/networth", headers=auth_headers).json()["lines"][0]
    assert line["category_slug"] == "trousers"
    matched = client.get("/api/assets", params={"category": "trousers"},
                         headers=auth_headers).json()["assets"]
    assert line["image_asset_id"] == matched[0]["id"]

    thumb = client.get(f"/api/assets/{line['image_asset_id']}/thumbnail",
                       headers=auth_headers)
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/webp"


def test_dashboard_reports_the_saved_net_worth(client, auth_headers):
    cats = _category(client, auth_headers, "Transport")
    _item(client, auth_headers, "Bicycle", cats, quantity_owned=1,
          estimated_unit_cost_minor=750000)

    client.get("/api/networth", headers=auth_headers)  # records the figure
    body = client.get("/api/dashboard/summary", headers=auth_headers).json()
    assert body["net_worth_minor"] == 750000


def test_net_worth_requires_signing_in(client):
    assert client.get("/api/networth").status_code in (401, 403)
