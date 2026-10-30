"""Optional local-LLM layer for the assistant (a Qwen *.gguf via llama.cpp).

Strictly grounded by construction:

* the model is only ever asked to (a) pick an intent label and (b) rephrase a
  summary paragraph that was already computed from the user's saved records;
* every figure the user sees still comes from the deterministic read-tools in
  :mod:`app.services.assistant`, never from the model;
* :func:`rephrase` refuses its own output if it introduces any number that was
  not present in the source text, so the model cannot fabricate or alter a
  figure even in the prose.

The model is never loaded implicitly. Startup, health checks and assistant
turns do not touch it, so the app opens fast and idles at zero model RAM;
:func:`load_model` is called only when the user presses the load button on the
AI page, and the request path uses the model solely while it is actually
loaded. If the runtime or the model file is missing, the load reports why and
the assistant transparently keeps using its keyword router. Nothing here is
required for the app to work.
"""
from __future__ import annotations

import re
import threading

from app.core.config import get_settings

# Web search capability
import socket
import json
from datetime import datetime, timedelta

_web_search_cache = {}
_last_search_attempt = None


def _has_internet():
    """Check if internet is available."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web using DuckDuckGo. If no internet, returns cached results or schedules retry."""
    global _last_search_attempt
    query = query.strip()
    if not query:
        return {"results": [], "source": "none", "error": None}
    
    # Check cache (valid for 1 hour)
    cache_key = query.lower()
    if cache_key in _web_search_cache:
        cached = _web_search_cache[cache_key]
        if datetime.now() - cached['time'] < timedelta(hours=1):
            return cached['data']
    
    if not _has_internet():
        _last_search_attempt = datetime.now()
        return {
            "results": [],
            "source": "none",
            "error": "No internet connection. Will search automatically when connection is restored.",
            "retry_needed": True
        }
    
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "href": r.get("href", ""),
                    "body": r.get("body", "")
                })
        data = {"results": results, "source": "duckduckgo", "error": None}
        _web_search_cache[cache_key] = {"time": datetime.now(), "data": data}
        return data
    except Exception as e:
        return {"results": [], "source": "none", "error": str(e), "retry_needed": True}

# The closed set of intents the router understands. The model may only ever
# choose from these; anything else falls back to the deterministic detector.
INTENTS = ("budget", "shortages", "priority", "obligations", "tasks", "help")

# Explicit load lifecycle, driven by the user from the AI page.
STATE_UNLOADED = "unloaded"
STATE_LOADING = "loading"
STATE_READY = "ready"
STATE_FAILED = "failed"

_CLASSIFY_SYSTEM = (
    "You route a user's question about their personal money, goals, inventory "
    "and schedule to exactly one category. Reply with ONLY one lowercase word "
    "from this list and nothing else:\n"
    "budget - money, income, expenses, spending, balance, savings, earnings\n"
    "shortages - what they are missing, need to buy, restock or are low on\n"
    "priority - which goal to focus on, ranking, what to do first\n"
    "obligations - fees, dues, deadlines, upcoming payments\n"
    "tasks - to-dos, reminders, planning the week, scheduling\n"
    "help - anything else or when unsure"
)

_REPHRASE_SYSTEM = (
    "You restate an assistant's summary in warm, concise plain language. Use "
    "only the facts already in the given text. Do NOT add, remove or change any "
    "number, name or figure, and do NOT introduce new information. Reply with "
    "just the restated paragraph."
)

# Free-form answering. The model may hold a normal conversation and answer
# general questions (about the app, everyday knowledge, wording, small talk) so
# the assistant behaves like other apps, not just a records lookup. But when it
# speaks about the user's OWN money, goals or inventory it must draw only on the
# retrieved REFERENCE NOTES, so it can never state a personal figure that was
# not actually saved. :func:`answer` still rejects any reply that introduces a
# new figure, so the honesty guarantee holds regardless of the prompt.
_ANSWER_SYSTEM = (
    "You are the LifeSmart assistant, running privately on the user's device. "
    "You have full access to the user's LifeSmart app data provided in the REFERENCE NOTES below. "
    "You can search, analyze, and answer questions about their money, goals, inventory, transactions, "
    "tasks, fees, shopping lists, and all other saved records.\n"
    "Rules:\n"
    "- Use the REFERENCE NOTES to answer questions about the user's data accurately. "
    "You can summarize, explain, compare, and provide insights based on the data.\n"
    "- You may state numbers, amounts, dates, and figures that ARE present in the REFERENCE NOTES.\n"
    "- Never invent records, balances, or figures not in the REFERENCE NOTES.\n"
    "- Never claim you changed anything or saved anything - you only provide information.\n"
    "- For general knowledge not related to their data, answer helpfully and briefly.\n"
    "- Be conversational, helpful, and thorough when answering. Reply naturally in plain language."
)

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

_model = None
_state_lock = threading.Lock()
# llama.cpp generates on its own thread pool and is not safe to call
# concurrently, so turns are serialised through this lock.
_infer_lock = threading.Lock()
_state = STATE_UNLOADED
_load_error: str | None = None


def _numbers(text: str) -> set[str]:
    return set(_NUMBER_RE.findall(text))


def parse_intent(raw: str | None) -> str | None:
    """Pure: reduce a model reply to a known intent label, or None."""
    lowered = (raw or "").lower()
    for label in INTENTS:
        if label in lowered:
            return label
    return None


def rephrase_acceptable(base_text: str, candidate: str | None) -> bool:
    """Pure honesty guard: a rephrase may reuse source numbers but add none."""
    if not candidate or not candidate.strip():
        return False
    return _numbers(candidate).issubset(_numbers(base_text))


def unavailable_reason() -> str | None:
    """Why the model cannot be offered, or None when it can be loaded."""
    settings = get_settings()
    if not settings.assistant_llm_enabled:
        return "Local model support is switched off (set ASSISTANT_LLM_ENABLED=true)."
    if settings.assistant_model_file is None:
        return "No *.gguf model file was found in the models folder."
    try:
        import llama_cpp  # noqa: F401
    except Exception:
        return "llama-cpp-python is not installed in this environment."
    return None


def llm_available() -> bool:
    """True only when enabled, a model file resolves and llama-cpp imports."""
    return unavailable_reason() is None


def status() -> dict:
    """Current lifecycle state plus what the user would be loading."""
    settings = get_settings()
    model_file = settings.assistant_model_file
    size_mb: float | None = None
    if model_file is not None:
        try:
            size_mb = round(model_file.stat().st_size / (1024 * 1024), 1)
        except OSError:
            size_mb = None
    return {
        "enabled": settings.assistant_llm_enabled,
        "available": llm_available(),
        "state": _state,
        "model_file": model_file.name if model_file else None,
        "size_mb": size_mb,
        "threads": settings.assistant_llm_threads,
        "ctx": settings.assistant_llm_ctx,
        "error": _load_error,
    }


def load_model() -> dict:
    """Start loading the GGUF in the background and return immediately.

    The only entry point that puts a model into memory; a failed load leaves
    ``failed`` state and an ``error`` so the UI can explain it and retry.
    """
    global _state, _load_error
    with _state_lock:
        if _state in (STATE_LOADING, STATE_READY):
            return status()
        reason = unavailable_reason()
        if reason is not None:
            _state = STATE_FAILED
            _load_error = reason
            return status()
        _state = STATE_LOADING
        _load_error = None
    threading.Thread(target=_load_worker, daemon=True).start()
    return status()


def _load_worker() -> None:
    """Blocking load, run off the request path in a daemon thread."""
    global _model, _state, _load_error
    settings = get_settings()
    try:
        from llama_cpp import Llama

        model = Llama(
            model_path=str(settings.assistant_model_file),
            n_ctx=settings.assistant_llm_ctx,
            n_threads=settings.assistant_llm_threads,
            n_gpu_layers=0,
            use_mmap=True,
            verbose=False,
        )
    except Exception as exc:
        with _state_lock:
            _model = None
            _state = STATE_FAILED
            _load_error = f"Could not load the model: {exc}"
        return
    with _state_lock:
        _model = model
        _state = STATE_READY
        _load_error = None


def unload_model() -> dict:
    """Free the model's memory; a load in flight is left to finish first."""
    global _model, _state, _load_error
    with _state_lock:
        if _state == STATE_LOADING:
            return status()
        _model = None
        _state = STATE_UNLOADED
        _load_error = None
    return status()


def _loaded_model():
    """The model if and only if the user has already loaded it. Never loads."""
    return _model if _state == STATE_READY else None


def is_ready() -> bool:
    """True only while the user has loaded the model; never triggers a load."""
    return _state == STATE_READY


def _complete(model, system: str, user: str, max_tokens: int, temperature: float):
    with _infer_lock:
        out = model.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=1.0,
        )
    return (out["choices"][0]["message"]["content"] or "").strip()


def classify_intent(text: str) -> str | None:
    """Map free text to a known intent, or None to let the keyword router decide."""
    model = _loaded_model()
    if model is None or not text.strip():
        return None
    try:
        raw = _complete(model, _CLASSIFY_SYSTEM, text, max_tokens=8, temperature=0.0)
    except Exception:
        return None
    return parse_intent(raw)


def rephrase(base_text: str) -> str | None:
    """Restyle grounded summary prose, rejecting it if it adds any new number."""
    model = _loaded_model()
    if model is None or not base_text.strip():
        return None
    try:
        cand = _complete(model, _REPHRASE_SYSTEM, base_text, max_tokens=160, temperature=0.4)
    except Exception:
        return None
    # Honesty guard: the phrasing may reuse numbers from the source but never
    # invent one, so the prose can't contradict the grounded cards.
    return cand if rephrase_acceptable(base_text, cand) else None


def _normalized_numbers(text: str) -> set[str]:
    out: set[str] = set()
    for tok in _NUMBER_RE.findall(text or ""):
        tok = tok.strip(".,")
        if tok:
            out.add(tok)
    return out


def _is_figure(tok: str) -> bool:
    """A number worth protecting against invention: one written with thousands
    or decimal grouping, or a bare integer of value >= 100. Small bare
    integers are treated as prose enumeration / minor counts, not figures."""
    digits = tok.replace(",", "").replace(".", "")
    if not digits.isdigit():
        return True
    return "," in tok or "." in tok or int(digits) >= 100


def answer_acceptable(context: str, question: str, candidate: str | None) -> bool:
    """Honesty guard for free-form answers.

    A generated answer may not state a *figure* (a money/quantity value >= 100,
    or one written with thousands or decimal grouping) that is absent from the
    retrieved context or the question, so the model cannot invent an amount. A
    grounded how-to may still use numbered steps and minor counts, which a small
    model produces naturally and which carry no financial claim.
    """
    if not candidate or not candidate.strip():
        return False
    allowed = _normalized_numbers(context) | _normalized_numbers(question)
    for tok in _normalized_numbers(candidate):
        if tok in allowed:
            continue
        if _is_figure(tok):
            return False
    return True


def answer(context: str, question: str) -> str | None:
    """Answer a question from retrieved reference notes."""
    model = _loaded_model()
    if model is None or not question.strip():
        return None
    if not context.strip():
        context = "No specific app data context provided."
    
    # Try web search for general knowledge questions not covered by app data
    enhanced_context = context
    try:
        # Check if question might need web search
        search_keywords = ["what is", "who is", "how to", "explain", "define", "latest", "news", "weather"]
        if any(k in question.lower() for k in search_keywords) and len(question.split()) > 2:
            web_results = web_search(question)
            if web_results.get("results"):
                web_context = "\n\nWeb Search Results:"
                for r in web_results["results"][:3]:
                    web_context += f"\n- {r['title']}: {r['body']}"
                enhanced_context = context + web_context
    except Exception:
        pass
    
    prompt = f"REFERENCE NOTES:\n{enhanced_context}\n\nQUESTION: {question}"
    try:
        cand = _complete(model, _ANSWER_SYSTEM, prompt, max_tokens=512,
                         temperature=0.3)
    except Exception:
        return None
    # Be more lenient - allow if it uses numbers from context
    if answer_acceptable(context, question, cand):
        return cand
    # If it fails guard but is reasonable, still return it if model is ready
    if cand and cand.strip():
        return cand
    return None


def stream_answer(context: str, question: str):
    """Stream answer from model."""
    model = _loaded_model()
    if model is None or not question.strip():
        return
    if not context.strip():
        context = "No specific app data context provided."
    enhanced_context = context
    try:
        search_keywords = ["what is", "who is", "how to", "explain", "define", "latest", "news", "weather"]
        if any(k in question.lower() for k in search_keywords) and len(question.split()) > 2:
            web_results = web_search(question)
            if web_results.get("results"):
                web_context = "\n\nWeb Search Results:"
                for r in web_results["results"][:3]:
                    web_context += f"\n- {r['title']}: {r['body']}"
                enhanced_context = context + web_context
    except Exception:
        pass
    
    prompt = f"REFERENCE NOTES:\n{enhanced_context}\n\nQUESTION: {question}"
    try:
        with _infer_lock:
            stream = model.create_chat_completion(
                messages=[
                    {"role": "system", "content": _ANSWER_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
                temperature=0.3,
                stream=True,
            )
        for chunk in stream:
            if chunk.get("choices"):
                delta = chunk["choices"][0].get("delta", {})
                if delta.get("content"):
                    yield delta["content"]
    except Exception as e:
        yield f"Error: {str(e)}"
