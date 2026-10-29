"""Restoring an export: the round trip, and the refusals that protect it.

An export is only a backup if it can come back, and a restore is the one
operation in the app that can destroy records the person is looking at. So most
of these tests are about the second half of that sentence: an archive that
cannot be accounted for is refused *completely*, leaving the account exactly as
it was, and an archive that can be restored comes back with its values rather
than merely its row counts.
"""
import base64
import io
import json
import zipfile
from datetime import date

from PIL import Image


def _make_image(path, fmt="JPEG", size=(160, 120), color=(90, 90, 120)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, fmt)
    return path


# --- a small life, connected the way the app connects it -------------------

def _life(client, headers):
    """Rows that reference each other: a priced item, an account, a spent and
    reversed transaction, a goal with a contribution, a fee part-paid, a task
    with a time. Returns what the caller needs to name them later."""
    cats = client.get("/api/inventory/categories", headers=headers).json()
    trousers = next(c["id"] for c in cats if c["name"] == "Clothing")
    item = client.post("/api/inventory/items", json={
        "name": "Chino trousers", "category_id": trousers, "quantity_owned": 2,
        "target_quantity": 4, "estimated_unit_cost_minor": 150000,
        "price_verified": True, "price_source": "Town shop",
    }, headers=headers).json()
    # A second item with no price at all: its null has to survive as a null.
    unpriced = client.post("/api/inventory/items", json={
        "name": "Study lamp", "category_id": trousers, "quantity_owned": 1,
    }, headers=headers).json()
    account = client.post("/api/accounts", json={
        "name": "M-PESA", "type": "mpesa", "mpesa_number": "0712345678",
        "balance_minor": 125050,
    }, headers=headers).json()
    expense = client.post("/api/transactions", json={
        "type": "expense", "amount_minor": 300000, "occurred_on": str(date.today()),
        "account_id": account["id"], "description": "two trousers",
        "idempotency_key": "exp-1",
    }, headers=headers).json()
    reversal = client.post(
        f"/api/transactions/{expense['id']}/reverse", headers=headers).json()
    goal = client.post("/api/goals", json={
        "name": "New laptop", "type": "money", "target_amount_minor": 6000000,
        "deadline": "2026-12-01",
    }, headers=headers).json()
    client.post(f"/api/goals/{goal['id']}/contributions", json={
        "amount_minor": 100000, "occurred_on": str(date.today()),
    }, headers=headers)
    fee = client.post("/api/student/fees", json={
        "name": "Semester tuition", "category": "tuition",
        "amount_due_minor": 4000000, "due_on": "2026-11-30",
    }, headers=headers).json()
    client.post(f"/api/student/fees/{fee['id']}/payments", json={
        "amount_minor": 1500000, "idempotency_key": "fee-pay-1",
    }, headers=headers)
    task = client.post("/api/tasks", json={
        "title": "Pay rent", "due_on": "2026-11-05", "due_time": "18:30",
        "remind_before_days": 3,
    }, headers=headers).json()
    client.put("/api/notifications/preferences", json={"savings_nudges": False},
               headers=headers)
    return {
        "item": item, "unpriced": unpriced, "account": account,
        "expense": expense, "reversal": reversal, "goal": goal, "fee": fee,
        "task": task,
    }


def _rows(client, headers):
    """Per owned table, how many rows the account holds. Read through the
    settings surface a person sees, not through the database."""
    privacy = client.get("/api/settings", headers=headers).json()["privacy"]
    return {t["key"]: t["rows"] for t in privacy["stored"]}


def _archive(client, headers):
    """The export as the person's Downloads folder holds it, base64-encoded the
    way the restore route asks for it."""
    resp = client.get("/api/account/export", headers=headers)
    assert resp.status_code == 200
    return base64.b64encode(resp.content).decode()


def _payload(client, headers):
    resp = client.get("/api/account/export", headers=headers)
    return json.loads(zipfile.ZipFile(io.BytesIO(resp.content)).read("data.json"))


def _tampered(client, headers, table, rows):
    """A re-written archive: same shape, different rows. Built the way a
    hand-edited or half-downloaded file would look."""
    payload = _payload(client, headers)
    payload["tables"][table] = rows
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.json", json.dumps(payload))
    return base64.b64encode(buf.getvalue()).decode()


def _zip_bytes(payload):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.json", json.dumps(payload))
    return base64.b64encode(buf.getvalue()).decode()


def _preview(client, headers, archive, **kwargs):
    return client.post("/api/account/restore/preview",
                       json={"archive_base64": archive, **kwargs}, headers=headers)


def _restore(client, headers, archive, word="RESTORE"):
    return client.post("/api/account/restore",
                       json={"archive_base64": archive, "confirm": word},
                       headers=headers)


def _refused(client, headers, archive, before):
    """400, a reason, and not one row moved."""
    resp = _restore(client, headers, archive)
    assert resp.status_code == 400, resp.text
    assert "Nothing was changed" in resp.json()["detail"]
    assert _rows(client, headers) == before
    return resp.json()["detail"]


# --- the round trip --------------------------------------------------------

def test_a_reset_backup_comes_back_whole(client, auth_headers):
    mine = _life(client, auth_headers)
    archive = _archive(client, auth_headers)
    expected = _rows(client, auth_headers)

    client.post("/api/account/reset", json={"confirm": "RESET"}, headers=auth_headers)
    assert sum(_rows(client, auth_headers).values()) < sum(expected.values())

    resp = _restore(client, auth_headers, archive)
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["written_total"] == sum(expected.values())
    for key, count in expected.items():
        assert _rows(client, auth_headers)[key] == count, key


def test_amounts_come_back_as_they_were_recorded(client, auth_headers):
    mine = _life(client, auth_headers)
    archive = _archive(client, auth_headers)
    client.post("/api/account/reset", json={"confirm": "RESET"}, headers=auth_headers)
    _restore(client, auth_headers, archive)

    accounts = client.get("/api/accounts", headers=auth_headers).json()
    restored = next(a for a in accounts if a["name"] == "M-PESA")
    assert restored["balance_minor"] == 125050
    # Not 1250.50, and not 12505000: minor units survived the trip unchanged.
    assert restored["mpesa_number"] == "+254712345678"

    goals = client.get("/api/goals", headers=auth_headers).json()
    laptop = next(g for g in goals if g["name"] == "New laptop")
    assert laptop["target_amount_minor"] == 6000000


def test_a_value_never_recorded_stays_unrecorded(client, auth_headers):
    """The lamp was added without a price. A restore must not turn that unknown
    into a zero, which would make the shortage look free."""
    _life(client, auth_headers)
    archive = _archive(client, auth_headers)
    client.post("/api/account/reset", json={"confirm": "RESET"}, headers=auth_headers)
    _restore(client, auth_headers, archive)

    items = client.get("/api/inventory/items", headers=auth_headers).json()["items"]
    lamp = next(i for i in items if i["name"] == "Study lamp")
    assert lamp["estimated_unit_cost_minor"] is None
    assert lamp["target_quantity"] is None


def test_dates_and_times_come_back_as_dates(client, auth_headers):
    """The export flattens them to strings; a restore has to hand them back to
    columns that only accept real dates and times."""
    _life(client, auth_headers)
    archive = _archive(client, auth_headers)
    client.post("/api/account/reset", json={"confirm": "RESET"}, headers=auth_headers)
    _restore(client, auth_headers, archive)

    task = client.get("/api/tasks", headers=auth_headers).json()[0]
    assert task["due_on"] == "2026-11-05"
    assert task["due_time"] == "18:30:00"
    goal = next(g for g in client.get("/api/goals", headers=auth_headers).json()
                if g["name"] == "New laptop")
    assert goal["deadline"] == "2026-12-01"


def test_restored_rows_still_belong_to_the_they_belong_to(client, auth_headers):
    """Ids are allocated afresh, so every reference has to be re-pointed. A
    contribution that lands on the wrong goal is worse than one that is lost."""
    _life(client, auth_headers)
    archive = _archive(client, auth_headers)
    client.post("/api/account/reset", json={"confirm": "RESET"}, headers=auth_headers)
    _restore(client, auth_headers, archive)

    goals = client.get("/api/goals", headers=auth_headers).json()
    laptop = next(g for g in goals if g["name"] == "New laptop")
    contributions = client.get(
        f"/api/goals/{laptop['id']}/contributions", headers=auth_headers).json()
    assert [c["amount_minor"] for c in contributions] == [100000]

    fees = client.get("/api/student/fees", headers=auth_headers).json()
    tuition = next(f for f in fees if f["name"] == "Semester tuition")
    assert tuition["amount_paid_minor"] == 1500000

    items = client.get("/api/inventory/items", headers=auth_headers).json()["items"]
    trousers = next(i for i in items if i["name"] == "Chino trousers")
    cats = client.get("/api/inventory/categories", headers=auth_headers).json()
    assert trousers["category_id"] in {c["id"] for c in cats}


def test_a_reversed_transaction_still_points_at_what_it_cancelled(
        client, auth_headers):
    """A reversal refers to its own table, which no ordering of tables can
    satisfy: it is filled in once every row has an id to point at."""
    mine = _life(client, auth_headers)
    archive = _archive(client, auth_headers)
    client.post("/api/account/reset", json={"confirm": "RESET"}, headers=auth_headers)
    _restore(client, auth_headers, archive)

    txs = client.get("/api/transactions", headers=auth_headers).json()["transactions"]
    by_id = {t["id"]: t for t in txs}
    reversals = [t for t in txs if t.get("reversal_of_id")]
    assert len(reversals) == 1
    original = by_id[reversals[0]["reversal_of_id"]]
    assert original["description"] == "two trousers"
    assert original["reversed"] is True


def test_the_notification_switches_come_back_too(client, auth_headers):
    """The switches are rows like any other, and they gate the alerts the same
    records produce - so a restore has to bring both halves back together."""
    _life(client, auth_headers)
    assert client.get("/api/notifications/alerts", headers=auth_headers).json()[
        "hidden_by_preferences"] == ["savings"]
    archive = _archive(client, auth_headers)

    client.post("/api/account/reset", json={"confirm": "RESET"}, headers=auth_headers)
    _restore(client, auth_headers, archive)

    prefs = client.get("/api/notifications/preferences", headers=auth_headers).json()
    assert prefs["savings_nudges"] is False
    alerts = client.get("/api/notifications/alerts", headers=auth_headers).json()
    assert alerts["hidden_by_preferences"] == ["savings"]
    assert alerts["count"] > 0


def test_the_picture_link_survives_while_the_picture_does(client, auth_headers,
                                                        assets_root):
    image = _make_image(assets_root / "clothing" / "trousers" / "chino.jpg")
    client.post("/api/assets/scan", json={}, headers=auth_headers)
    assets = client.get("/api/assets", params={"category": "trousers"},
                        headers=auth_headers).json()["assets"]
    assert assets, "the scan should have indexed the image"
    cats = client.get("/api/inventory/categories", headers=auth_headers).json()
    client.post("/api/inventory/items", json={
        "name": "Chino trousers", "category_id": cats[0]["id"], "quantity_owned": 1,
        "image_asset_id": assets[0]["id"],
    }, headers=auth_headers)

    archive = _archive(client, auth_headers)
    resp = _restore(client, auth_headers, archive)
    assert resp.status_code == 200, resp.text
    assert resp.json()["photo_links_kept"] == 1
    assert resp.json()["photo_links_cleared"] == 0
    assert image.is_file()


def test_a_link_to_a_picture_that_is_not_here_is_cleared_not_guessed(
        client, auth_headers):
    """The picture index is machine-wide and is not part of an export. A
    restored item must not end up showing somebody else's photograph."""
    cats = client.get("/api/inventory/categories", headers=auth_headers).json()
    client.post("/api/inventory/items", json={
        "name": "Chino trousers", "category_id": cats[0]["id"], "quantity_owned": 1,
        "image_asset_id": "00000000-0000-0000-0000-000000000000",
    }, headers=auth_headers)
    archive = _archive(client, auth_headers)

    resp = _restore(client, auth_headers, archive)
    assert resp.status_code == 200, resp.text
    assert resp.json()["photo_links_cleared"] == 1
    assert "picture" in resp.json()["warnings"][0]
    # The record itself is back; only the link to a missing file is gone.
    items = client.get("/api/inventory/items", headers=auth_headers).json()["items"]
    assert [i["name"] for i in items] == ["Chino trousers"]


def test_the_amounts_and_their_currency_travel_together(client, auth_headers):
    """Every figure in the archive was written in one currency. Restoring it
    onto an account set to another would silently reinterpret the lot."""
    _life(client, auth_headers)
    archive = _archive(client, auth_headers)

    client.patch("/api/auth/me", json={"currency": "UGX"}, headers=auth_headers)
    preview = _preview(client, auth_headers, archive).json()
    assert preview["currency_of_origin"] == "KES"
    assert preview["current_currency"] == "UGX"
    assert any("KES" in w and "UGX" in w for w in preview["warnings"])

    resp = _restore(client, auth_headers, archive)
    assert resp.status_code == 200, resp.text
    assert resp.json()["currency_changed_from"] == "UGX"
    assert resp.json()["currency"] == "KES"
    account = client.get("/api/accounts", headers=auth_headers).json()[0]
    assert account["balance_minor"] == 125050


def test_a_restore_leaves_the_sign_in_and_the_name_alone(client, auth_headers):
    """A reset kept these, so a restore has nothing to bring back - and
    overwriting the identity of an account that is already signed in would be
    its own surprise."""
    _life(client, auth_headers)
    archive = _archive(client, auth_headers)
    client.patch("/api/auth/me", json={"full_name": "Nowhere Near The Backup"},
                 headers=auth_headers)

    resp = _restore(client, auth_headers, archive)
    assert resp.status_code == 200, resp.text
    me = client.get("/api/auth/me", headers=auth_headers).json()
    assert me["full_name"] == "Nowhere Near The Backup"
    assert me["email"] == "test@example.com"
    assert "account sign-in" in resp.json()["kept"]


def test_restoring_another_accounts_backup_does_not_collide(
        client, auth_headers, second_user_headers):
    """Both accounts' rows start at id 1. Reusing the archive's keys would
    clash with this account's own rows, so ids are allocated here instead."""
    _life(client, auth_headers)
    theirs = _archive(client, auth_headers)
    _life(client, second_user_headers)

    resp = _restore(client, second_user_headers, theirs)
    assert resp.status_code == 200, resp.text

    goals = client.get("/api/goals", headers=auth_headers).json()
    assert [g["name"] for g in goals] == ["New laptop"], "the other account moved"
    # Nothing of the owner's was touched: their ids are still theirs.
    assert sum(_rows(client, second_user_headers).values()) > 0


def test_only_the_callers_own_rows_are_replaced(client, auth_headers,
                                               second_user_headers):
    _life(client, auth_headers)
    _life(client, second_user_headers)
    theirs_before = _rows(client, second_user_headers)
    archive = _archive(client, auth_headers)

    assert _restore(client, auth_headers, archive).status_code == 200
    assert _rows(client, second_user_headers) == theirs_before


def test_restore_refuses_without_the_word(client, auth_headers):
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    archive = _archive(client, auth_headers)

    resp = _restore(client, auth_headers, archive, word="RESTOR")
    assert resp.status_code == 400
    assert "Type RESTORE to confirm" in resp.json()["detail"]
    assert _rows(client, auth_headers) == before


def test_restore_requires_signing_in(client):
    assert client.post("/api/account/restore",
                       json={"archive_base64": "AAA", "confirm": "RESTORE"},
                       ).status_code in (401, 403)
    assert client.post("/api/account/restore/preview",
                       json={"archive_base64": "AAA"},
                       ).status_code in (401, 403)


# --- refusals: nothing arrives half-restored -------------------------------

def test_an_empty_upload_is_refused(client, auth_headers):
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    for archive, reason in [("", "No file was sent"), ("!!!", "could not be read")]:
        detail = _refused(client, auth_headers, archive, before)
        assert reason in detail


def test_a_file_that_is_not_an_export_is_refused(client, auth_headers):
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    not_a_zip = base64.b64encode(b"just some text, not a zip file").decode()
    assert "not a zip archive" in _refused(client, auth_headers, not_a_zip, before)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("README.txt", "a zip of something else")
    other = base64.b64encode(buf.getvalue()).decode()
    assert "no data.json" in _refused(client, auth_headers, other, before)


def test_a_file_not_written_by_the_export_is_refused(client, auth_headers):
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    payload = _payload(client, auth_headers)
    payload["meta"]["kind"] = "someone_elses_dump"
    detail = _refused(client, auth_headers, _zip_bytes(payload), before)
    assert "not written by LifeSmart" in detail


def test_records_this_build_does_not_know_are_not_dropped(client, auth_headers):
    """Almost certainly a newer app's export. Restoring it would mean quietly
    losing the tables this build cannot name."""
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    detail = _refused(
        client, auth_headers,
        _tampered(client, auth_headers, "time_machines", [{"id": 1}]), before)
    assert "time_machines" in detail


def test_a_column_this_build_does_not_store_is_refused(client, auth_headers):
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    goals = _payload(client, auth_headers)["tables"]["goals"]
    goals[0]["warp_factor"] = 9
    detail = _refused(client, auth_headers,
                      _tampered(client, auth_headers, "goals", goals), before)
    assert "warp_factor" in detail


def test_a_fractional_amount_is_refused_not_rounded(client, auth_headers):
    """125050 is KES 1,250.50. A value with a fraction of a minor unit did not
    come from this app, and rounding it would change what was recorded."""
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    goals = _payload(client, auth_headers)["tables"]["goals"]
    goals[0]["target_amount_minor"] = 6000000.5
    detail = _refused(client, auth_headers,
                      _tampered(client, auth_headers, "goals", goals), before)
    assert "whole number of minor units" in detail


def test_money_written_as_words_is_refused(client, auth_headers):
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    goals = _payload(client, auth_headers)["tables"]["goals"]
    goals[0]["target_amount_minor"] = "six million"
    _refused(client, auth_headers,
             _tampered(client, auth_headers, "goals", goals), before)


def test_a_reference_to_a_record_that_is_not_in_the_file_is_refused(
        client, auth_headers):
    """A goal aimed at a missing item would come back broken, and the person
    would only find out by clicking it."""
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    goals = _payload(client, auth_headers)["tables"]["goals"]
    goals[0]["inventory_item_id"] = 987654
    detail = _refused(client, auth_headers,
                      _tampered(client, auth_headers, "goals", goals), before)
    assert "inventory item" in detail and "does not contain" in detail


def test_a_record_that_would_belong_to_nothing_is_refused(client, auth_headers):
    """category_id cannot be blank on an item, so it is not something a restore
    may invent."""
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    items = _payload(client, auth_headers)["tables"]["inventory_items"]
    items[0]["category_id"] = None
    detail = _refused(client, auth_headers,
                      _tampered(client, auth_headers, "inventory_items", items),
                      before)
    assert "no inventory category to belong to" in detail


def test_an_archive_that_contradicts_itself_is_refused(client, auth_headers):
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    items = _payload(client, auth_headers)["tables"]["inventory_items"]
    _refused(client, auth_headers,
             _tampered(client, auth_headers, "inventory_items", [items[0], items[0]]),
             before)


def test_two_copies_of_a_one_row_table_are_refused(client, auth_headers):
    """An account holds one set of notification preferences. Two would make the
    alerts computation guess which half applies."""
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    prefs = _payload(client, auth_headers)["tables"]["notification_preferences"]
    two = [dict(prefs[0], id=1), dict(prefs[0], id=2)]
    detail = _refused(client, auth_headers,
                      _tampered(client, auth_headers, "notification_preferences", two),
                      before)
    assert "only one" in detail


def test_a_status_this_build_has_never_seen_is_refused(client, auth_headers):
    """Enum columns are read back as names. An unknown one would blow up the
    next page that tried to label it."""
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    goals = _payload(client, auth_headers)["tables"]["goals"]
    goals[0]["status"] = "melting"
    detail = _refused(client, auth_headers,
                      _tampered(client, auth_headers, "goals", goals), before)
    assert "melting" in detail


def test_a_bad_date_is_refused(client, auth_headers):
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    goals = _payload(client, auth_headers)["tables"]["goals"]
    goals[0]["deadline"] = "sometime in december"
    detail = _refused(client, auth_headers,
                      _tampered(client, auth_headers, "goals", goals), before)
    assert "readable as a date" in detail


# --- the preview ------------------------------------------------------------

def test_the_preview_reads_and_writes_nothing(client, auth_headers):
    _life(client, auth_headers)
    before = _rows(client, auth_headers)
    archive = _archive(client, auth_headers)

    resp = _preview(client, auth_headers, archive)
    assert resp.status_code == 200, resp.text
    assert _rows(client, auth_headers) == before
    # Both sides are stated, per table: one total could hide a missing kind.
    body = resp.json()
    assert body["current_total"] == sum(before.values())
    assert body["archive_total"] == sum(before.values())
    goals = next(t for t in body["tables"] if t["key"] == "goals")
    assert goals["archive_rows"] == goals["current_rows"] == 1
    assert body["generated_at"] is not None


def test_the_preview_says_what_would_be_lost(client, auth_headers):
    """Records made after the export are not in it, and a restore throws them
    away. That has to be visible before the button, not after."""
    _life(client, auth_headers)
    archive = _archive(client, auth_headers)
    client.post("/api/tasks", json={"title": "Book a taxi for tomorrow"},
                headers=auth_headers)

    body = _preview(client, auth_headers, archive).json()
    assert body["current_total"] > body["archive_total"]
    assert any("replace" in w and "after this export" in w for w in body["warnings"])


def test_an_archive_holding_nothing_is_named_as_one(client, auth_headers):
    """An archive whose every table is empty is what restoring nothing looks
    like, and it should not arrive dressed up as a restore."""
    payload = _payload(client, auth_headers)
    for key in payload["tables"]:
        payload["tables"][key] = []
    archive = _zip_bytes(payload)
    client.post("/api/tasks", json={"title": "Buy charcoal"}, headers=auth_headers)

    body = _preview(client, auth_headers, archive).json()
    assert body["archive_total"] == 0
    assert any("no records at all" in w for w in body["warnings"])


def test_the_preview_refuses_a_bad_archive_the_same_way(client, auth_headers):
    _life(client, auth_headers)
    goals = _payload(client, auth_headers)["tables"]["goals"]
    goals[0]["target_amount_minor"] = 6000000.5
    resp = _preview(client, auth_headers,
                    _tampered(client, auth_headers, "goals", goals))
    assert resp.status_code == 400
    assert "Nothing was changed" in resp.json()["detail"]


def test_the_preview_is_not_a_perm(client, auth_headers):
    """A preview earned no trust: the restore re-reads and re-checks whatever it
    is actually given."""
    _life(client, auth_headers)
    archive = _archive(client, auth_headers)
    assert _preview(client, auth_headers, archive).status_code == 200

    goals = _payload(client, auth_headers)["tables"]["goals"]
    goals[0]["status"] = "melting"
    tampered = _tampered(client, auth_headers, "goals", goals)
    assert _restore(client, auth_headers, tampered).status_code == 400
    assert client.get("/api/goals", headers=auth_headers).json()[0]["status"] != "melting"
