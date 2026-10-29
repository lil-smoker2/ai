"""AI assistant tests.

The core acceptance bar: the assistant reasons over saved data only, never
invents records, never infers price/seller from a photo, and never writes
anything without an explicit user confirmation.
"""
from datetime import date, timedelta

from PIL import Image


def _make_image(path, fmt="JPEG", size=(160, 120)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (120, 60, 30)).save(path, fmt)
    return path


def _ask(client, headers, message, conversation_id=None, asset_id=None):
    body = {"message": message}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    if asset_id is not None:
        body["asset_id"] = asset_id
    resp = client.post("/api/assistant/messages", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _metric(card, label):
    for item in card["items"]:
        if item["label"] == label:
            return item
    raise AssertionError(f"metric {label!r} not found in {card}")


def test_suggestions_and_auth(client, auth_headers):
    prompts = client.get("/api/assistant/suggestions", headers=auth_headers).json()
    assert any("wardrobe" in p for p in prompts)
    assert client.post("/api/assistant/messages", json={"message": "hi"}).status_code == 401


def test_intent_router_handles_phrasing_variations():
    from app.services import assistant as a

    # Stemming + stopwording means varied wording still routes to one intent.
    assert a._detect_intent("how much did I spend this month", False) == "budget"
    assert a._detect_intent("what am I missing", False) == "shortages"
    assert a._detect_intent("which goals should i prioritise", False) == "priority"
    assert a._detect_intent("when are my fees due", False) == "obligations"
    assert a._detect_intent("turn my goals into weekly tasks", False) == "tasks"
    assert a._detect_intent("banana helicopter", False) == "help"


def test_app_help_question_explains_a_screen(client, auth_headers):
    reply = _ask(client, auth_headers,
                 "How do I add an expense?")["assistant_message"]
    # Routed to the app-help knowledge base, not a data tool: names the screen,
    # returns no grounded cards and invents no figure.
    assert "Money" in reply["content"]
    assert reply["cards"] in (None, [])
    assert reply["proposal"] is None


def test_app_help_privacy_question(client, auth_headers):
    reply = _ask(client, auth_headers,
                 "Where is my data stored?")["assistant_message"]
    assert "machine" in reply["content"].lower()


def test_greeting_gets_warm_opener_not_a_report(client, auth_headers):
    # A bare "hi" (and friends) is answered with a greeting, no data cards.
    for hello in ("hi", "Hello!", "hey there", "how are you", "good morning"):
        reply = _ask(client, auth_headers, hello)["assistant_message"]
        assert reply["cards"] in (None, []), hello
        assert reply["proposal"] is None, hello
        assert "saved records" in reply["content"].lower(), hello


def test_greeting_is_not_hijacked_by_loaded_model(client, auth_headers, monkeypatch):
    # Even if a loaded model misroutes a greeting to a data intent, the router
    # answers small talk first, so "hi" never opens a budget report.
    from app.services import llm

    monkeypatch.setattr(llm, "is_ready", lambda: True)
    monkeypatch.setattr(llm, "classify_intent", lambda text: "budget")
    reply = _ask(client, auth_headers, "hi")["assistant_message"]
    assert reply["cards"] in (None, [])
    assert "transaction" not in reply["content"].lower()


def test_greeting_with_a_real_question_still_routes(client, auth_headers):
    # "hey" followed by an actual query must not be swallowed by the greeter.
    reply = _ask(client, auth_headers, "hey, what am I missing in my wardrobe?")
    assert not reply["assistant_message"]["content"].startswith("Hey there")


def test_unknown_question_falls_back_to_guidance(client, auth_headers):
    reply = _ask(client, auth_headers, "qwerty zxcv plugh")["assistant_message"]
    # Transparent about its two modes rather than dead-ending or guessing.
    assert "saved records" in reply["content"].lower()
    assert reply["cards"] in (None, [])


def test_unmatched_question_uses_loaded_model(client, auth_headers, monkeypatch):
    # A user who pressed Load, with a model that grounds a reply on retrieved
    # project context, gets a real answer for a question the router can't match.
    from app.services import llm

    monkeypatch.setattr(llm, "is_ready", lambda: True)
    monkeypatch.setattr(
        llm, "answer",
        lambda context, question: "I can look at your money, goals and inventory.",
    )
    reply = _ask(client, auth_headers, "tell me a joke about the weather")[
        "assistant_message"
    ]
    assert reply["content"] == "I can look at your money, goals and inventory."
    assert reply["cards"] in (None, [])
    assert reply["proposal"] is None


def test_unmatched_question_falls_back_when_model_refuses(client, auth_headers, monkeypatch):
    # If the model is ready but its answer fails the honesty guard (returns None)
    # the assistant keeps the deterministic guidance instead of inventing text.
    from app.services import llm

    monkeypatch.setattr(llm, "is_ready", lambda: True)
    monkeypatch.setattr(llm, "answer", lambda context, question: None)
    reply = _ask(client, auth_headers, "tell me a joke about the weather")[
        "assistant_message"
    ]
    assert "saved records" in reply["content"].lower()


def test_budget_reports_no_data_instead_of_inventing(client, auth_headers):
    reply = _ask(client, auth_headers, "Help me budget for this month.")["assistant_message"]
    assert "transaction" in reply["content"].lower()
    card = reply["cards"][0]
    # No accounts initialised -> balance stays null/unknown, never a fake zero.
    assert _metric(card, "Total available")["minor"] is None


def test_budget_grounds_figures_in_saved_transactions(client, auth_headers):
    today = str(date.today())
    acct = client.post("/api/accounts", json={"name": "Cash", "type": "cash"},
                       headers=auth_headers).json()
    client.post(f"/api/accounts/{acct['id']}/initialize",
                json={"balance_minor": 50000}, headers=auth_headers)
    client.post("/api/transactions", json={"type": "income", "amount_minor": 20000,
                "account_id": acct["id"], "category": "allowance", "occurred_on": today},
                headers=auth_headers)
    client.post("/api/transactions", json={"type": "expense", "amount_minor": 7500,
                "account_id": acct["id"], "category": "food", "occurred_on": today},
                headers=auth_headers)

    reply = _ask(client, auth_headers, "how much did I spend this month")["assistant_message"]
    card = reply["cards"][0]
    assert _metric(card, "Income")["minor"] == 20000
    assert _metric(card, "Expenses")["minor"] == 7500
    assert _metric(card, "Total available")["minor"] == 50000 + 20000 - 7500


def test_shortage_price_unknown_is_not_fabricated(client, auth_headers):
    # Users are seeded with default categories; reuse the existing "Clothing".
    cats = client.get("/api/inventory/categories", headers=auth_headers).json()
    cat = next(c for c in cats if c["name"].lower() == "clothing")
    client.post("/api/inventory/items", json={
        "name": "Chinos", "category_id": cat["id"], "quantity_owned": 1,
        "target_quantity": 3, "estimated_unit_cost_minor": None,
    }, headers=auth_headers)

    reply = _ask(client, auth_headers, "What am I missing?")["assistant_message"]
    rows = next(c for c in reply["cards"] if c["kind"] == "list")["rows"]
    chinos = next(r for r in rows if r["heading"] == "Chinos")
    assert chinos["badge"] == "need 2"
    assert "price needed" in chinos["lines"]
    # Unpriced shortage => total stays null, never a guessed number.
    total = _metric(next(c for c in reply["cards"] if c["kind"] == "metrics"),
                    "Estimated cost to target")
    assert total["minor"] is None


def test_priority_ranks_by_saved_deadlines(client, auth_headers):
    yesterday = str(date.today() - timedelta(days=1))
    client.post("/api/goals", json={"name": "Laptop fund", "type": "money",
                "target_amount_minor": 100000, "priority": "critical",
                "deadline": yesterday}, headers=auth_headers)
    client.post("/api/goals", json={"name": "Long read", "type": "custom",
                "priority": "low"}, headers=auth_headers)

    reply = _ask(client, auth_headers, "Which goals should I prioritize?")["assistant_message"]
    rows = next(c for c in reply["cards"] if c["kind"] == "list")["rows"]
    assert rows[0]["heading"].endswith("Laptop fund")  # overdue + critical first
    assert any("overdue" in " ".join(r["lines"]).lower() for r in rows)


def test_obligations_never_claim_a_fee_paid(client, auth_headers):
    fee = client.post("/api/student/fees", json={"name": "Semester tuition",
                    "category": "tuition", "amount_due_minor": 100000,
                    "due_on": str(date.today() + timedelta(days=5))},
                    headers=auth_headers).json()
    client.post(f"/api/student/fees/{fee['id']}/payments",
                json={"amount_minor": 40000, "idempotency_key": "pay-1"},
                headers=auth_headers)

    reply = _ask(client, auth_headers, "What fees are due?")["assistant_message"]
    rows = next(c for c in reply["cards"] if c["kind"] == "list")["rows"]
    tuition = next(r for r in rows if r["heading"] == "Semester tuition")
    assert tuition["badge"] == "partial"           # not "paid"
    assert tuition["minor"] == 60000               # outstanding, from records


def test_search_finds_inventory_by_name(client, auth_headers):
    # A question naming a specific thing no single intent captures still gets a
    # grounded answer built from the matching saved record.
    cats = client.get("/api/inventory/categories", headers=auth_headers).json()
    cat = next(c for c in cats if c["name"].lower() == "clothing")
    client.post("/api/inventory/items", json={
        "name": "Sunglasses", "category_id": cat["id"], "quantity_owned": 2,
        "target_quantity": 4, "estimated_unit_cost_minor": None,
    }, headers=auth_headers)
    client.post("/api/inventory/items", json={
        "name": "Beanie", "category_id": cat["id"], "quantity_owned": 1,
    }, headers=auth_headers)

    reply = _ask(client, auth_headers, "where are my sunglasses?")["assistant_message"]
    assert "searched" in reply["content"].lower()
    rows = next(c for c in reply["cards"] if c["kind"] == "list")["rows"]
    hit = next(r for r in rows if r["heading"] == "Sunglasses")
    assert hit["badge"] == "2/4"
    assert "price not recorded" in hit["lines"]
    # The unrelated Beanie is not pulled in.
    assert all(r["heading"] != "Beanie" for r in rows)


def test_search_finds_goal_and_shows_saved_amount(client, auth_headers):
    client.post("/api/goals", json={"name": "Emergency fund", "type": "money",
                "target_amount_minor": 100000}, headers=auth_headers)
    reply = _ask(client, auth_headers,
                 "how much is left for the emergency fund")
    msg = reply["assistant_message"]
    rows = next(c for c in msg["cards"] if c["kind"] == "list")["rows"]
    goal = next(r for r in rows if r["heading"] == "Emergency fund")
    assert goal["minor"] == 100000            # outstanding, straight from records
    assert any("saved" in l for l in goal["lines"])


def test_search_reports_no_matches_instead_of_inventing(client, auth_headers):
    # A question whose words match no record is answered honestly: no rows, no
    # fabricated figures.
    reply = _ask(client, auth_headers, "quantum flux capacitor")
    msg = reply["assistant_message"]
    assert "found nothing" in msg["content"].lower()
    assert "saved records" in msg["content"].lower()
    assert msg["cards"] in (None, [])


def test_assistant_chats_about_itself_without_a_model(client, auth_headers):
    # Non-database, everyday questions get a real conversational answer even
    # when no local model is loaded (like other apps), instead of the guide.
    who = _ask(client, auth_headers, "who are you?")["assistant_message"]
    assert "assistant" in who["content"].lower()
    assert who["cards"] in (None, [])
    assert who["proposal"] is None

    can = _ask(client, auth_headers, "what can you do")["assistant_message"]
    assert "budget" in can["content"].lower() or "goal" in can["content"].lower()
    assert can["cards"] in (None, [])

    priv = _ask(client, auth_headers, "are you connected to the internet")[
        "assistant_message"
    ]
    assert "device" in priv["content"].lower()


def test_loaded_model_can_answer_a_non_database_question(client, auth_headers, monkeypatch):
    # With a model loaded, a general question the router knows nothing about is
    # handed to the model rather than the records guide.
    from app.services import llm

    monkeypatch.setattr(llm, "is_ready", lambda: True)
    monkeypatch.setattr(
        llm, "answer",
        lambda context, question: "Paris is the capital of France.",
    )
    reply = _ask(client, auth_headers, "what is the capital of france")[
        "assistant_message"
    ]
    assert reply["content"] == "Paris is the capital of France."
    assert reply["cards"] in (None, [])


def test_tasks_proposal_requires_confirmation_then_writes(client, auth_headers):
    client.post("/api/goals", json={"name": "Gym", "type": "custom"},
                headers=auth_headers)
    sent = _ask(client, auth_headers, "Turn my goals into weekly tasks.")
    proposal = sent["assistant_message"]["proposal"]
    assert proposal["kind"] == "create_tasks_from_goals"
    assert proposal["status"] == "pending"

    # Nothing was written before confirming.
    assert client.get("/api/tasks", headers=auth_headers).json() == []

    done = client.post(f"/api/assistant/proposals/{proposal['id']}/confirm",
                       headers=auth_headers).json()
    assert done["proposal"]["status"] == "confirmed"
    tasks = client.get("/api/tasks", headers=auth_headers).json()
    assert len(tasks) == 1
    assert tasks[0]["status"] == "pending"  # approved by user, now active

    # A confirmed proposal cannot run twice.
    again = client.post(f"/api/assistant/proposals/{proposal['id']}/confirm",
                        headers=auth_headers)
    assert again.status_code == 409


def test_image_analysis_proposes_category_without_price(client, auth_headers, assets_root):
    _make_image(assets_root / "clothing" / "trousers" / "product.jpg")
    client.post("/api/assets/scan", json={}, headers=auth_headers)
    asset = client.get("/api/assets", headers=auth_headers).json()["assets"][0]

    reply = _ask(client, auth_headers, "Analyze this product image.",
                 asset_id=asset["id"])
    proposal = reply["assistant_message"]["proposal"]
    assert proposal["kind"] == "add_inventory_item"
    # Price is never inferred from a photograph.
    assert proposal["payload"]["estimated_unit_cost_minor"] is None
    assert "price" in reply["assistant_message"]["content"].lower() or \
           "seller" in reply["assistant_message"]["content"].lower()

    done = client.post(f"/api/assistant/proposals/{proposal['id']}/confirm",
                       headers=auth_headers).json()
    assert done["proposal"]["status"] == "confirmed"
    items = client.get("/api/inventory/items", headers=auth_headers).json()["items"]
    saved = next(i for i in items if i["image_asset_id"] == asset["id"])
    assert saved["estimated_unit_cost_minor"] is None  # still no invented price


def test_cross_user_isolation(client, auth_headers, second_user_headers):
    client.post("/api/goals", json={"name": "Private", "type": "custom"},
                headers=auth_headers)
    sent = _ask(client, auth_headers, "Turn my goals into weekly tasks.")
    convo_id = sent["conversation_id"]
    proposal_id = sent["assistant_message"]["proposal"]["id"]

    assert client.get(f"/api/assistant/conversations/{convo_id}",
                      headers=second_user_headers).status_code == 404
    assert client.post(f"/api/assistant/proposals/{proposal_id}/confirm",
                       headers=second_user_headers).status_code == 404


def test_conversation_history_persists(client, auth_headers):
    first = _ask(client, auth_headers, "hello")
    cid = first["conversation_id"]
    _ask(client, auth_headers, "what am I missing", conversation_id=cid)
    detail = client.get(f"/api/assistant/conversations/{cid}",
                        headers=auth_headers).json()
    # 2 user + 2 assistant messages
    assert detail["conversation"]["message_count"] == 4
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][1]["role"] == "assistant"
