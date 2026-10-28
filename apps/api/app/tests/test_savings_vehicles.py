"""Savings vehicle tests: dated rates, projections, holdings and betting notes.

The rules these tests hold are the honesty rules the feature is built on: a
rate stands only with the date it was checked, a projection is arithmetic on
figures the person supplied and records nothing, a betting site is refused any
projected return, and a card with records on it cannot be deleted.
"""
from datetime import date


def _vehicle(client, headers, **overrides):
    body = {"name": "Ziidi", "kind": "mpesa"}
    body.update(overrides)
    return client.post("/api/earnings/vehicles", json=body, headers=headers)


# --- Creating a vehicle ---

def test_create_vehicle_keeps_what_was_typed(client, auth_headers):
    resp = _vehicle(
        client, auth_headers,
        url="https://www.ziidi.co.ke/",
        rate_percent=10.75,
        rate_checked_on="2026-10-01",
    )
    assert resp.status_code == 201
    row = resp.json()
    assert row["name"] == "Ziidi"
    assert row["kind"] == "mpesa"
    assert row["url"] == "https://www.ziidi.co.ke/"
    assert row["rate_percent"] == 10.75
    assert row["rate_checked_on"] == "2026-10-01"
    # Nothing was recorded, which is not the same as a record of nothing.
    assert row["net_in_minor"] is None
    assert row["gain_minor"] is None


def test_name_is_stripped_and_required(client, auth_headers):
    row = _vehicle(client, auth_headers, name="  M-Shwari  ").json()
    assert row["name"] == "M-Shwari"
    assert _vehicle(client, auth_headers, name="   ").status_code == 422


def test_rate_needs_the_date_it_was_checked(client, auth_headers):
    # An undated percentage is exactly the number read as current a year later.
    resp = _vehicle(client, auth_headers, rate_percent=9.0)
    assert resp.status_code == 422
    assert "date you checked it" in resp.json()["detail"][0]["msg"]


def test_a_date_with_no_rate_dates_nothing(client, auth_headers):
    row = _vehicle(client, auth_headers, rate_checked_on="2026-10-01").json()
    assert row["rate_percent"] is None
    assert row["rate_checked_on"] is None


def test_only_http_links_are_kept(client, auth_headers):
    # The link is handed to a real browser, so nothing that can run is stored.
    assert _vehicle(client, auth_headers, url="javascript:alert(1)").status_code == 422
    assert _vehicle(client, auth_headers, url="not a link").status_code == 422
    row = _vehicle(client, auth_headers, url="  https://betika.com/  ")
    assert row.json()["url"] == "https://betika.com/"


def test_a_betting_site_carries_no_rate(client, auth_headers):
    """A gamble gets a name and a link, never a percentage to project from."""
    row = _vehicle(
        client, auth_headers, kind="betting", url="https://www.aviator.co/",
        rate_percent=12.0, rate_checked_on="2026-10-01",
    ).json()
    assert row["rate_percent"] is None
    assert row["rate_checked_on"] is None
    assert row["url"] == "https://www.aviator.co/"


# --- Projection ---

def test_projection_is_simple_interest_on_the_recorded_rate(client, auth_headers):
    vid = _vehicle(
        client, auth_headers, rate_percent=10.75, rate_checked_on="2026-10-01"
    ).json()["id"]
    resp = client.post(
        f"/api/earnings/vehicles/{vid}/project",
        json={"amount_minor": 1_000_000, "months": 12},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    out = resp.json()
    # KES 10,000.00 at 10.75% a year: one year is 107,500 minor.
    assert out["interest_minor"] == 107_500
    assert out["total_minor"] == 1_107_500
    # Half a year halves it: no compounding is invented.
    six = client.post(
        f"/api/earnings/vehicles/{vid}/project",
        json={"amount_minor": 1_000_000, "months": 6},
        headers=auth_headers,
    ).json()
    assert six["interest_minor"] == 53_750


def test_projection_states_its_assumptions(client, auth_headers):
    vid = _vehicle(client, auth_headers, rate_percent=9.5,
                   rate_checked_on="2026-09-01").json()["id"]
    out = client.post(
        f"/api/earnings/vehicles/{vid}/project",
        json={"amount_minor": 500_000, "months": 3},
        headers=auth_headers,
    ).json()
    joined = " ".join(out["assumptions"])
    assert "9.5% a year" in joined
    assert "2026-09-01" in joined
    assert "offline" in joined
    assert "Nothing was recorded and no money moved" in joined


def test_projection_refuses_without_a_rate(client, auth_headers):
    vid = _vehicle(client, auth_headers).json()["id"]
    resp = client.post(
        f"/api/earnings/vehicles/{vid}/project",
        json={"amount_minor": 1000, "months": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "No rate recorded" in resp.json()["detail"]


def test_projection_refuses_a_bet(client, auth_headers):
    vid = _vehicle(client, auth_headers, kind="betting").json()["id"]
    resp = client.post(
        f"/api/earnings/vehicles/{vid}/project",
        json={"amount_minor": 1000, "months": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "no rate to project from" in resp.json()["detail"]


def test_projection_needs_a_positive_amount_and_a_span(client, auth_headers):
    vid = _vehicle(client, auth_headers, rate_percent=8.0,
                   rate_checked_on="2026-10-01").json()["id"]
    for body in ({"amount_minor": 0, "months": 1},
                 {"amount_minor": -5, "months": 1},
                 {"amount_minor": 100, "months": 0},
                 {"amount_minor": 100, "months": 601}):
        assert client.post(f"/api/earnings/vehicles/{vid}/project",
                           json=body, headers=auth_headers).status_code == 422


# --- Holdings ---

def test_holding_value_needs_the_day_it_was_valued(client, auth_headers):
    resp = _vehicle(client, auth_headers, kind="shares", value_minor=450_000)
    assert resp.status_code == 422
    assert "when a holding was valued" in resp.json()["detail"][0]["msg"]

    row = _vehicle(client, auth_headers, kind="shares", units=120,
                   value_minor=450_000, valued_on="2026-10-20").json()
    assert row["units"] == 120
    assert row["value_minor"] == 450_000
    # Shares pay no quoted annual rate, so none is kept on them.
    assert row["rate_percent"] is None


def test_gain_compares_a_valuation_with_the_records(client, auth_headers):
    vid = _vehicle(client, auth_headers, kind="shares", units=120,
                   value_minor=450_000, valued_on="2026-10-20").json()["id"]
    _flow(client, auth_headers, vid, direction="in", amount_minor=400_000)
    _flow(client, auth_headers, vid, direction="out", amount_minor=50_000)
    row = _one(client, auth_headers, vid)
    # Worth 450k now with 50k already taken out against 400k put in: 100k gain.
    assert row["put_in_minor"] == 400_000
    assert row["taken_out_minor"] == 50_000
    assert row["net_in_minor"] == 350_000
    assert row["gain_minor"] == 100_000


def test_gain_is_null_until_a_value_is_entered(client, auth_headers):
    vid = _vehicle(client, auth_headers, kind="shares").json()["id"]
    _flow(client, auth_headers, vid, direction="in", amount_minor=400_000)
    row = _one(client, auth_headers, vid)
    assert row["net_in_minor"] == 400_000
    # Nobody has valued it, so nothing about its worth is claimed.
    assert row["gain_minor"] is None


# --- Flow records ---

def _flow(client, headers, vid, **overrides):
    body = {"direction": "in", "amount_minor": 5000, "occurred_on": "2026-10-05"}
    body.update(overrides)
    return client.post(f"/api/earnings/vehicles/{vid}/flows", json=body,
                       headers=headers)


def _one(client, headers, vid):
    rows = client.get("/api/earnings/vehicles", headers=headers).json()
    return next(v for v in rows if v["id"] == vid)


def test_flows_total_what_went_in_and_came_back(client, auth_headers):
    vid = _vehicle(client, auth_headers).json()["id"]
    _flow(client, auth_headers, vid, amount_minor=5000, note="staked")
    _flow(client, auth_headers, vid, direction="out", amount_minor=2000,
          occurred_on="2026-10-06")
    _flow(client, auth_headers, vid, amount_minor=500, occurred_on="2026-10-07")
    row = _one(client, auth_headers, vid)
    assert row["put_in_minor"] == 5500
    assert row["taken_out_minor"] == 2000
    assert row["net_in_minor"] == 3500


def test_flow_list_is_newest_first(client, auth_headers):
    vid = _vehicle(client, auth_headers).json()["id"]
    _flow(client, auth_headers, vid, occurred_on="2026-10-05")
    _flow(client, auth_headers, vid, occurred_on="2026-10-07")
    _flow(client, auth_headers, vid, occurred_on="2026-10-06")
    rows = client.get(f"/api/earnings/vehicles/{vid}/flows",
                      headers=auth_headers).json()
    assert [r["occurred_on"] for r in rows] == ["2026-10-07", "2026-10-06",
                                                "2026-10-05"]


def test_a_flow_needs_money_and_a_day(client, auth_headers):
    vid = _vehicle(client, auth_headers).json()["id"]
    assert _flow(client, auth_headers, vid, amount_minor=0).status_code == 422
    assert _flow(client, auth_headers, vid, direction="sideways").status_code == 422


def test_flows_do_not_move_account_balances(client, auth_headers):
    """A vehicle note is not a ledger entry, or the same money counts twice."""
    account = client.post(
        "/api/accounts",
        json={"name": "M-PESA", "type": "mpesa", "mpesa_number": "0712345678",
              "balance_minor": 300_000},
        headers=auth_headers,
    ).json()
    vid = _vehicle(client, auth_headers).json()["id"]
    _flow(client, auth_headers, vid, amount_minor=50_000)
    after = client.get("/api/accounts", headers=auth_headers).json()
    row = next(a for a in after if a["id"] == account["id"])
    assert row["balance_minor"] == 300_000


def test_deleting_a_flow_leaves_the_rest(client, auth_headers):
    vid = _vehicle(client, auth_headers).json()["id"]
    first = _flow(client, auth_headers, vid, amount_minor=5000).json()
    _flow(client, auth_headers, vid, amount_minor=1000, occurred_on="2026-10-08")
    assert client.delete(f"/api/earnings/vehicle-flows/{first['id']}",
                         headers=auth_headers).status_code == 204
    assert _one(client, auth_headers, vid)["net_in_minor"] == 1000


# --- Correcting and deleting a card ---

def test_update_replaces_the_card_so_an_emptied_rate_goes(client, auth_headers):
    vid = _vehicle(client, auth_headers, rate_percent=10.75,
                   rate_checked_on="2026-10-01").json()["id"]
    resp = client.put(f"/api/earnings/vehicles/{vid}",
                      json={"name": "KCB M-PESA", "kind": "mpesa"},
                      headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "KCB M-PESA"
    # The edit form shows every field, so leaving a rate out means removing it.
    assert resp.json()["rate_percent"] is None
    assert resp.json()["rate_checked_on"] is None


def test_update_applies_the_same_rules_as_creation(client, auth_headers):
    vid = _vehicle(client, auth_headers, rate_percent=10.75,
                   rate_checked_on="2026-10-01").json()["id"]
    resp = client.put(f"/api/earnings/vehicles/{vid}",
                      json={"name": "Ziidi", "kind": "mpesa", "rate_percent": 11},
                      headers=auth_headers)
    assert resp.status_code == 422
    # The refused rewrite left the card exactly as it was.
    assert _one(client, auth_headers, vid)["rate_percent"] == 10.75


def test_a_vehicle_with_records_cannot_be_deleted(client, auth_headers):
    vid = _vehicle(client, auth_headers).json()["id"]
    flow = _flow(client, auth_headers, vid, amount_minor=5000,
                 note="saved in").json()
    resp = client.delete(f"/api/earnings/vehicles/{vid}", headers=auth_headers)
    assert resp.status_code == 409
    assert "Remove them first" in resp.json()["detail"]
    assert client.get("/api/earnings/vehicles", headers=auth_headers).json()

    client.delete(f"/api/earnings/vehicle-flows/{flow['id']}", headers=auth_headers)
    assert client.delete(f"/api/earnings/vehicles/{vid}",
                         headers=auth_headers).status_code == 204


# --- Ownership ---

def test_vehicles_are_scoped_to_their_owner(client, auth_headers,
                                            second_user_headers):
    vid = _vehicle(client, auth_headers, rate_percent=9.0,
                   rate_checked_on="2026-10-01").json()["id"]
    flow_id = _flow(client, auth_headers, vid, amount_minor=5000).json()["id"]

    assert client.get("/api/earnings/vehicles",
                      headers=second_user_headers).json() == []
    for call in (
        lambda: client.put(f"/api/earnings/vehicles/{vid}",
                           json={"name": "Theirs", "kind": "bank"},
                           headers=second_user_headers),
        lambda: client.delete(f"/api/earnings/vehicles/{vid}",
                              headers=second_user_headers),
        lambda: client.post(f"/api/earnings/vehicles/{vid}/flows",
                            json={"direction": "in", "amount_minor": 1,
                                  "occurred_on": "2026-10-01"},
                            headers=second_user_headers),
        lambda: client.get(f"/api/earnings/vehicles/{vid}/flows",
                           headers=second_user_headers),
        lambda: client.post(f"/api/earnings/vehicles/{vid}/project",
                            json={"amount_minor": 1, "months": 1},
                            headers=second_user_headers),
        lambda: client.delete(f"/api/earnings/vehicle-flows/{flow_id}",
                              headers=second_user_headers),
    ):
        assert call().status_code == 404

    # Nothing was changed through the other account.
    assert _one(client, auth_headers, vid)["net_in_minor"] == 5000


def test_unknown_vehicle_is_404_not_a_blank_card(client, auth_headers):
    assert client.post("/api/earnings/vehicles/9999/flows",
                       json={"direction": "in", "amount_minor": 1,
                             "occurred_on": str(date.today())},
                       headers=auth_headers).status_code == 404
    assert client.post("/api/earnings/vehicles/9999/project",
                       json={"amount_minor": 1, "months": 1},
                       headers=auth_headers).status_code == 404
