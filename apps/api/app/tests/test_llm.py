"""Tests for the assistant LLM adapter's model-independent guarantees.

The load lifecycle is the important part: nothing here may ever put a model into
memory implicitly, so these assert on the state machine as well as the pure
helpers. They run whether or not llama-cpp or a model file is present.
"""
import pytest

from app.services import llm


@pytest.fixture(autouse=True)
def _restore_model_state():
    """Each test starts and ends with no model loaded."""
    with llm._state_lock:
        saved = (llm._model, llm._state, llm._load_error)
    yield
    with llm._state_lock:
        llm._model, llm._state, llm._load_error = saved


def test_llm_disabled_in_tests():
    # conftest forces ASSISTANT_LLM_ENABLED=false, so the assistant stays deterministic.
    assert llm.llm_available() is False


def test_status_starts_unloaded():
    st = llm.status()
    assert st["state"] == llm.STATE_UNLOADED
    assert st["enabled"] is False
    assert st["available"] is False
    assert st["error"] is None


def test_classify_intent_noop_when_unavailable():
    # With the LLM off, classification defers to the keyword router (returns None).
    assert llm.classify_intent("how much did I spend this month?") is None


def test_rephrase_noop_when_unavailable():
    assert llm.rephrase("Some grounded summary.") is None


def test_request_path_never_loads_the_model():
    # The whole point of the load button: answering a turn must not touch RAM.
    llm.classify_intent("which goals should I prioritize?")
    llm.rephrase("You saved 30,000 across 2 goals.")
    assert llm._model is None
    assert llm._state == llm.STATE_UNLOADED


def test_load_reports_why_the_model_cannot_run():
    # Unavailable here (feature off), so the load fails honestly instead of
    # spawning a thread that could never succeed.
    st = llm.load_model()
    assert st["state"] == llm.STATE_FAILED
    assert "switched off" in st["error"]
    assert llm._model is None


def test_unload_returns_to_unloaded_and_clears_error():
    llm.load_model()
    st = llm.unload_model()
    assert st["state"] == llm.STATE_UNLOADED
    assert st["error"] is None


def test_model_endpoints(client, auth_headers):
    status = client.get("/api/assistant/model", headers=auth_headers)
    assert status.status_code == 200
    assert status.json()["state"] == "unloaded"

    failed = client.post("/api/assistant/model/load", headers=auth_headers).json()
    assert failed["state"] == "failed" and "switched off" in failed["error"]

    back = client.post("/api/assistant/model/unload", headers=auth_headers).json()
    assert back["state"] == "unloaded" and back["error"] is None


def test_model_status_requires_auth(client):
    assert client.get("/api/assistant/model").status_code == 401
    assert client.post("/api/assistant/model/load").status_code == 401


def test_parse_intent_accepts_known_labels():
    assert llm.parse_intent("BUDGET") == "budget"
    assert llm.parse_intent("  shortages ") == "shortages"
    assert llm.parse_intent("I think priority is best") == "priority"


def test_parse_intent_rejects_unknown():
    assert llm.parse_intent("cooking") is None
    assert llm.parse_intent("") is None
    assert llm.parse_intent(None) is None


def test_rephrase_acceptable_reuses_source_numbers():
    base = "You saved 30,000 across 2 goals."
    assert llm.rephrase_acceptable(base, "Nice — 30,000 saved over 2 goals!") is True


def test_rephrase_acceptable_rejects_invented_number():
    base = "You saved 30,000 across 2 goals."
    # The model hallucinated "5" — must be rejected so prose can't contradict cards.
    assert llm.rephrase_acceptable(base, "You saved 30,000 across 5 goals.") is False


def test_rephrase_acceptable_rejects_empty():
    assert llm.rephrase_acceptable("anything", "") is False
    assert llm.rephrase_acceptable("anything", None) is False


def test_answer_noop_when_unavailable():
    # With the LLM off, free-form answering defers to the deterministic fallback.
    assert llm.answer("REFERENCE NOTES: money help", "how do I add an expense?") is None


def test_answer_never_loads_the_model():
    # Like classify/rephrase, answering a turn must not implicitly put a model
    # into memory.
    llm.answer("some context 30,000", "what did I save?")
    assert llm._model is None
    assert llm._state == llm.STATE_UNLOADED
    assert llm.is_ready() is False


def test_answer_acceptable_reuses_context_numbers():
    context = "You have 2 active goals and saved 30,000."
    assert llm.answer_acceptable(
        context, "how am I doing?", "You've saved 30,000 across 2 goals."
    ) is True


def test_answer_acceptable_rejects_invented_number():
    context = "You have 2 active goals and saved 30,000."
    # The model hallucinated a figure that was never in the notes.
    assert llm.answer_acceptable(
        context, "how am I doing?", "You've saved 35,000 across 2 goals."
    ) is False


def test_answer_acceptable_allows_numbered_steps():
    # A grounded how-to may enumerate steps; small counts are not figures, so
    # they are not treated as invented amounts.
    context = "Adding an expense: Open Money and record a transaction."
    assert llm.answer_acceptable(
        context,
        "how do I log spending?",
        "1. Open Money.\n2. Add a transaction.\n3. Pick a category.",
    ) is True


def test_answer_acceptable_rejects_empty():
    assert llm.answer_acceptable("context", "q", "") is False
    assert llm.answer_acceptable("context", "q", None) is False
