"""Milestone 6: Settings, privacy export and the factory reset.

These cover the three things the milestone promises and the two rules that
matter most while doing it: an integration may never claim to work when it does
not, and an account's data must not cross to another account - including inside
an export file.
"""
import io
import json
import zipfile
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
    resp = client.post("/api/inventory/items",
                       json={"name": name, "category_id": category_id, **fields},
                       headers=headers)
    assert resp.status_code == 201
    return resp.json()


def _life(client, headers):
    """A small but connected life: an item with a price source, an account,
    a transaction drawn against it and a goal. Returns the item."""
    trousers = _category(client, headers, "Trousers")
    item = _item(client, headers, "Chino trousers", trousers,
                 quantity_owned=2, target_quantity=4,
                 estimated_unit_cost_minor=150000, price_verified=True,
                 price_source="Town shop")
    acct = client.post("/api/accounts", json={"name": "M-PESA", "type": "mpesa"},
                       headers=headers).json()
    tx = client.post("/api/transactions", json={
        "type": "expense", "amount_minor": 300000, "occurred_on": str(date.today()),
        "account_id": acct["id"], "description": "two trousers",
    }, headers=headers)
    assert tx.status_code in (200, 201)
    goal = client.post("/api/goals", json={
        "name": "New laptop", "type": "money", "target_amount_minor": 6000000,
        "priority": "high",
    }, headers=headers)
    assert goal.status_code in (200, 201)
    return item


def _zip(client, headers):
    resp = client.get("/api/account/export", headers=headers)
    assert resp.status_code == 200
    return resp, zipfile.ZipFile(io.BytesIO(resp.content))


def test_settings_returns_profile_preferences_and_storage(client, auth_headers):
    body = client.get("/api/settings", headers=auth_headers).json()

    assert body["profile"]["email"] == "test@example.com"
    assert body["profile"]["currency"] == "KES"
    assert {k: v for k, v in body["preferences"].items() if k.endswith("_alerts")}
    keys = {t["key"] for t in body["privacy"]["stored"]}
    assert {"inventory_items", "transactions", "net_worth_snapshots"} <= keys
    # Registering seeds the starter categories and nothing else.
    cats = next(t for t in body["privacy"]["stored"]
                if t["key"] == "inventory_categories")
    assert cats["rows"] == 7
    assert body["privacy"]["local_only"] is False
    assert "Nothing is uploaded to produce it" in body["export_note"]


def test_settings_never_shows_the_machine_path_to_a_hosted_user(
        client, auth_headers):
    """Rule 13 of the asset rules: no local paths through an API. The desktop
    app may show its own data directory; a hosted deployment must not."""
    body = client.get("/api/settings", headers=auth_headers).json()
    assert body["privacy"]["data_dir"] is None


def test_integrations_state_what_does_not_work(client, auth_headers):
    """The M6 acceptance criterion, as data: working integrations are
    distinguishable from manual ones and from those that do not exist."""
    body = client.get("/api/settings", headers=auth_headers).json()
    by_key = {i["key"]: i for i in body["integrations"]}

    assert {i["status"] for i in body["integrations"]} <= {
        "available", "on_demand", "manual", "not_configured", "unavailable"}
    # No payment or bank connection exists in this product.
    assert by_key["mpesa"]["status"] == "unavailable"
    assert by_key["bank"]["status"] == "unavailable"
    # Nothing leaves the device for reminders.
    assert by_key["delivery_channels"]["status"] == "not_configured"
    # You record prices and categories; the app fetches neither.
    assert by_key["price_sourcing"]["status"] == "manual"
    assert by_key["image_classification"]["status"] == "manual"
    # The local model is switched off in tests, so it must not claim to be up.
    assert by_key["local_model"]["status"] != "available"
    assert by_key["google_signin"]["status"] == "available"


def test_profile_is_editable_and_email_is_not(client, auth_headers):
    resp = client.patch("/api/auth/me", headers=auth_headers, json={
        "full_name": "David M", "currency": "USD", "is_student": False,
        "email": "attacker@example.com",
    })
    assert resp.status_code == 200
    me = resp.json()
    assert me["full_name"] == "David M"
    assert me["currency"] == "USD"
    assert me["is_student"] is False
    # Email is the sign-in identity; a field in the body must not move it.
    assert me["email"] == "test@example.com"

    assert client.patch("/api/auth/me", headers=auth_headers,
                        json={"full_name": "   "}).status_code == 422
    assert client.patch("/api/auth/me", headers=auth_headers,
                        json={"currency": "kenyan shillings"}).status_code == 422


def test_export_contains_every_row_the_caller_owns(client, auth_headers):
    _life(client, auth_headers)
    resp, zf = _zip(client, auth_headers)

    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    assert "lifesmart-export-" in resp.headers["content-disposition"]
    assert resp.headers["cache-control"] == "no-store"

    names = set(zf.namelist())
    assert {"README.txt", "manifest.json", "data.json"} <= names
    assert "csv/inventory_items.csv" in names

    data = json.loads(zf.read("data.json"))
    manifest = json.loads(zf.read("manifest.json"))
    items = data["tables"]["inventory_items"]
    assert items[0]["estimated_unit_cost_minor"] == 150000
    assert items[0]["price_verified"] is True
    assert items[0]["price_source"] == "Town shop"
    # Money columns are named so a spreadsheet cannot read 150000 as 150,000
    # units of currency.
    inventory_manifest = next(t for t in manifest["tables"]
                             if t["key"] == "inventory_items")
    assert "estimated_unit_cost_minor" in inventory_manifest["money_minor_columns"]
    assert manifest["row_total"] == sum(t["rows"] for t in manifest["tables"])


def test_export_keeps_unknowns_unknown(client, auth_headers):
    trousers = _category(client, auth_headers, "Trousers")
    _item(client, auth_headers, "Sofa", trousers, quantity_owned=1)

    _, zf = _zip(client, auth_headers)
    row = json.loads(zf.read("data.json"))["tables"]["inventory_items"][0]
    assert row["estimated_unit_cost_minor"] is None
    assert row["target_quantity"] is None
    assert row["price_source"] is None

    csv_lines = zf.read("csv/inventory_items.csv").decode().splitlines()
    header = csv_lines[0].split(",")
    cells = dict(zip(header, csv_lines[1].split(",")))
    # An empty cell, not 0 and not "N/A".
    assert cells["estimated_unit_cost_minor"] == ""


def test_export_hands_over_only_the_requesters_rows(client, auth_headers,
                                                   second_user_headers):
    _life(client, auth_headers)
    _item(client, second_user_headers, "Roommate mattress",
          _category(client, second_user_headers, "Household"),
          quantity_owned=1, estimated_unit_cost_minor=900000)

    _, first = _zip(client, auth_headers)
    data = json.loads(first.read("data.json"))
    blob = first.read("data.json") + first.read("manifest.json")

    names = [i["name"] for i in data["tables"]["inventory_items"]]
    assert names == ["Chino trousers"]
    assert "Roommate mattress" not in blob.decode()
    assert all(i["user_id"] == data["profile"]["id"]
               for i in data["tables"]["inventory_items"])
    # The shared picture index is not part of anyone's personal export.
    assert "assets" not in data["tables"]
    assert [e["key"] for e in json.loads(first.read("manifest.json"))["excluded"]] == [
        "assets", "asset_analyses"]


def test_export_carries_no_filesystem_path(client, auth_headers, assets_root):
    _make_image(assets_root / "clothing" / "trousers" / "chino.jpg")
    client.post("/api/assets/scan", json={}, headers=auth_headers)
    _life(client, auth_headers)

    _, zf = _zip(client, auth_headers)
    joined = b"".join(zf.read(n) for n in zf.namelist()
                      if not n.endswith("/"))
    assert str(assets_root).encode() not in joined
    assert b"/home/" not in joined


def test_export_requires_signing_in(client):
    assert client.get("/api/account/export").status_code in (401, 403)


def test_reset_refuses_without_the_word(client, auth_headers):
    _life(client, auth_headers)

    refused = client.post("/api/account/reset", json={"confirm": "yes"},
                          headers=auth_headers)
    assert refused.status_code == 400
    assert "Nothing was deleted" in refused.json()["detail"]
    assert client.get("/api/inventory/items", headers=auth_headers).json()["items"]

    blank = client.post("/api/account/reset", json={"confirm": ""},
                        headers=auth_headers)
    assert blank.status_code == 400


def test_reset_empties_the_account_and_keeps_the_sign_in(client, auth_headers):
    _life(client, auth_headers)
    assert client.get("/api/networth", headers=auth_headers).json()[
        "net_worth_minor"] == 300000

    resp = client.post("/api/account/reset", json={"confirm": "RESET"},
                       headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()
    assert result["deleted"]["inventory_items"] == 1
    assert result["deleted"]["transactions"] == 1
    assert result["deleted_total"] >= 4
    assert "picture index" in " ".join(result["kept"])

    assert client.get("/api/inventory/items", headers=auth_headers).json()["items"] == []
    assert client.get("/api/accounts", headers=auth_headers).json() == []
    assert client.get("/api/goals", headers=auth_headers).json() == []
    assert client.get("/api/tasks", headers=auth_headers).json() == []
    # Back to the starter categories, so the Inventory page is usable again.
    cats = client.get("/api/inventory/categories", headers=auth_headers).json()
    assert {c["name"] for c in cats} == {
        "Clothing", "Household", "Electronics", "Food", "Study materials",
        "Personal care", "Transport"}
    # The saved figure follows the now-empty inventory instead of the old one.
    assert client.get("/api/networth", headers=auth_headers).json()[
        "net_worth_minor"] == 0
    # The account itself survives: local desktop mode has no password to redo.
    me = client.get("/api/auth/me", headers=auth_headers)
    assert me.status_code == 200
    assert me.json()["email"] == "test@example.com"


def test_reset_touches_no_other_account(client, auth_headers, second_user_headers):
    _life(client, auth_headers)
    mattress = _item(client, second_user_headers, "Roommate mattress",
                     _category(client, second_user_headers, "Household"),
                     quantity_owned=1, estimated_unit_cost_minor=900000)

    client.post("/api/account/reset", json={"confirm": "RESET"},
                headers=auth_headers)

    kept = client.get(f"/api/inventory/items/{mattress['id']}",
                      headers=second_user_headers)
    assert kept.status_code == 200
    assert kept.json()["name"] == "Roommate mattress"
    other = client.get("/api/networth", headers=second_user_headers).json()
    assert other["net_worth_minor"] == 900000


def test_reset_leaves_picture_files_and_their_index(client, auth_headers,
                                                   assets_root):
    """The images are the user's; a reset of records must not throw the index
    away, and must not delete the files themselves."""
    image = _make_image(assets_root / "clothing" / "trousers" / "chino.jpg")
    client.post("/api/assets/scan", json={}, headers=auth_headers)
    before = client.get("/api/assets", params={"category": "trousers"},
                        headers=auth_headers).json()["assets"]
    _life(client, auth_headers)

    client.post("/api/account/reset", json={"confirm": "RESET"},
                headers=auth_headers)

    after = client.get("/api/assets", params={"category": "trousers"},
                       headers=auth_headers).json()["assets"]
    assert [a["id"] for a in after] == [a["id"] for a in before]
    assert image.is_file()


def test_reset_requires_signing_in(client):
    assert client.post("/api/account/reset", json={"confirm": "RESET"}
                       ).status_code in (401, 403)
