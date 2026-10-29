"""Replenishment forecasting: a run-out date only where the history supports one.

The whole point of this feature is that it never invents a rate. So most of
these cases assert silence - an item with no consumption, or consumption only
long ago, or only purchases, produces no forecast. Where a rate is real, the
arithmetic is checked on clean numbers so the projected date and the minor-unit
refill cost are exact, not approximate.
"""
from datetime import date, timedelta

WINDOW = 120


# --- helpers ---------------------------------------------------------------

def _category(client, headers):
    cats = client.get("/api/inventory/categories", headers=headers).json()
    return next(c for c in cats if c["name"].lower() == "clothing")


def _item(client, headers, **over):
    body = {
        "name": "Socks", "quantity_owned": 4, "target_quantity": 6,
        "category_id": _category(client, headers)["id"], **over,
    }
    resp = client.post("/api/inventory/items", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _use(client, headers, item_id, change, days_ago):
    """Record a quantity change dated days_ago back; returns the updated item."""
    body = {
        "change": change,
        "occurred_on": (date.today() - timedelta(days=days_ago)).isoformat(),
    }
    resp = client.post(
        f"/api/inventory/items/{item_id}/adjust-quantity", json=body, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _forecasts(client, headers):
    resp = client.get("/api/inventory/forecasts", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _only(payload):
    """Assert exactly one forecast and return it, naming what was there if not."""
    assert len(payload["forecasts"]) == 1, payload["forecasts"]
    return payload["forecasts"][0]


# --- silence: no rate, no date ---------------------------------------------

def test_a_fresh_account_has_nothing_to_forecast(client, auth_headers):
    assert _forecasts(client, auth_headers)["forecasts"] == []


def test_an_item_with_no_consumption_history_is_not_forecast(client, auth_headers):
    _item(client, auth_headers)  # opened, never used down
    assert _forecasts(client, auth_headers)["forecasts"] == []


def test_purchases_are_not_consumption(client, auth_headers):
    item = _item(client, auth_headers, quantity_owned=0)
    _use(client, auth_headers, item["id"], +4, days_ago=10)  # restock, not use
    assert _forecasts(client, auth_headers)["forecasts"] == []


def test_consumption_only_long_ago_is_not_forecast(client, auth_headers):
    item = _item(client, auth_headers)
    _use(client, auth_headers, item["id"], -1, days_ago=WINDOW + 80)
    assert _forecasts(client, auth_headers)["forecasts"] == []


# --- a real rate, projected exactly ----------------------------------------

def test_runout_date_comes_from_the_observed_rate(client, auth_headers):
    item = _item(client, auth_headers, quantity_owned=4)
    _use(client, auth_headers, item["id"], -1, days_ago=4)
    _use(client, auth_headers, item["id"], -1, days_ago=2)
    # total 2 over 4 days -> 0.5/day; owned now 2 -> 4 days to zero
    f = _only(_forecasts(client, auth_headers))
    assert f["consumption_per_day"] == 0.5
    assert f["consumption_events"] == 2
    assert f["window_days"] == 4
    assert f["days_to_zero"] == 4
    assert f["runout_on"] == (date.today() + timedelta(days=4)).isoformat()
    # Two events is not yet a repeating habit.
    assert f["confidence"] == "limited"


def test_a_repeating_habit_is_marked_steady(client, auth_headers):
    item = _item(client, auth_headers, quantity_owned=8)
    _use(client, auth_headers, item["id"], -2, days_ago=8)
    _use(client, auth_headers, item["id"], -1, days_ago=4)
    _use(client, auth_headers, item["id"], -1, days_ago=2)
    # total 4 over 8 days -> 0.5/day; owned now 4 -> 8 days
    f = _only(_forecasts(client, auth_headers))
    assert f["consumption_events"] == 3
    assert f["confidence"] == "steady"
    assert f["consumption_per_day"] == 0.5
    assert f["days_to_zero"] == 8


def test_only_the_recent_window_defines_the_rate(client, auth_headers):
    item = _item(client, auth_headers, quantity_owned=8)
    _use(client, auth_headers, item["id"], -1, days_ago=WINDOW + 40)  # outside
    _use(client, auth_headers, item["id"], -2, days_ago=8)           # inside
    _use(client, auth_headers, item["id"], -1, days_ago=4)           # inside
    _use(client, auth_headers, item["id"], -1, days_ago=2)           # inside
    # The 200-day event is excluded from both count and rate: in-window total 4
    # over 8 days -> 0.5/day. Owned is 8-1-2-1-1 = 3 (every change hits stock).
    f = _only(_forecasts(client, auth_headers))
    assert f["consumption_events"] == 3
    assert f["window_days"] == 8
    assert f["consumption_per_day"] == 0.5
    assert f["days_to_zero"] == 6  # owned 3 at 0.5/day


def test_zero_stock_is_out_now(client, auth_headers):
    item = _item(client, auth_headers, quantity_owned=1, target_quantity=3)
    _use(client, auth_headers, item["id"], -1, days_ago=5)
    f = _only(_forecasts(client, auth_headers))
    assert f["days_to_zero"] == 0
    assert f["runout_on"] == date.today().isoformat()
    assert f["restock_soon"] is True


# --- money stays minor units, and unknown stays unknown ---------------------

def test_refill_cost_uses_a_recorded_price(client, auth_headers):
    item = _item(client, auth_headers, quantity_owned=1, target_quantity=3,
                 estimated_unit_cost_minor=15000)
    _use(client, auth_headers, item["id"], -1, days_ago=2)
    # shortage 3 at 15000 minor = 45000, an integer minor amount
    f = _only(_forecasts(client, auth_headers))
    assert f["estimated_refill_cost_minor"] == 45000
    assert isinstance(f["estimated_refill_cost_minor"], int)


def test_refill_cost_is_null_when_no_price_was_recorded(client, auth_headers):
    item = _item(client, auth_headers, quantity_owned=1, target_quantity=3)
    _use(client, auth_headers, item["id"], -1, days_ago=2)
    f = _only(_forecasts(client, auth_headers))
    assert f["estimated_refill_cost_minor"] is None


def test_forecasts_are_ordered_soonest_first(client, auth_headers):
    slow = _item(client, auth_headers, name="Rice", quantity_owned=8)
    fast = _item(client, auth_headers, name="Milk", quantity_owned=2)
    _use(client, auth_headers, slow["id"], -1, days_ago=8)   # 1/8/day -> ~64 days
    _use(client, auth_headers, fast["id"], -1, days_ago=1)   # 1/day  -> 1 day
    order = [f["name"] for f in _forecasts(client, auth_headers)["forecasts"]]
    assert order == ["Milk", "Rice"]
