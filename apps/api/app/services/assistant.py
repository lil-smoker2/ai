"""Grounded assistant over validated read-tools, driven by an on-device NLP engine.

Routing is deterministic and runs without any language model, so it works on
every device: each message is normalised, stopworded and stem-tokenised
(see app.services.assistant_help), then scored against weighted concept tables.
A strong match on a data concept runs the matching read-tool; a "how do I use
the app" question matches the app-help knowledge base; otherwise a transparent
fallback explains what the assistant can do. When the user has loaded the
optional local Qwen model (app.services.llm) it can sharpen the intent, reword
a summary and answer otherwise-unmatched questions from retrieved project
context, but it never owns a figure. Every number reported is computed
from the user's own saved records; unknown values stay unknown; and any change
it wants to make is returned as a *proposal* that only persists after the user
confirms it. It never writes financial records, never infers a price or seller
from a photograph, and never fabricates data.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.models.asset import Asset
from app.models.finance import Account, Transaction
from app.models.goal import Goal, GoalContribution
from app.models.inventory import InventoryCategory, InventoryItem
from app.models.student import FeeObligation
from app.models.user import User
from app.services import assistant_help
from app.services import llm
from app.services.assistant_help import score, tokenize
from app.services.analysis import analyze_image

# Priority ordering for goal ranking (higher = more urgent).
_PRIORITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}

# A data intent must clear this much weighted-term overlap before we run a
# read-tool for it; below it the message is treated as app-help or unclear.
_DATA_THRESHOLD = 3

# Concepts behind each data intent. Order is the tie-break priority (an early
# intent wins on equal score), mirroring the original keyword router.
_DATA_CONCEPTS: list[tuple[str, dict[str, int]]] = [
    ("tasks", {"task": 4, "todo": 4, "schedule": 4, "reminder": 4,
               "plan": 3, "weekly": 3, "goals into": 3}),
    ("priority", {"prioritise": 5, "prioritize": 5, "priority": 4, "rank": 4,
                  "focus": 4, "first": 3, "order": 3, "which goal": 3}),
    ("obligations", {"fee": 5, "obligation": 5, "due": 4, "deadline": 4,
                     "tuition": 4, "semester": 3, "upcoming": 3, "payment": 3}),
    ("shortages", {"missing": 5, "shortage": 5, "restock": 5, "wardrobe": 4,
                   "need": 3, "low": 3, "stock": 3, "buy": 3, "afford": 2,
                   "complete": 2, "run out": 3}),
    ("budget", {"budget": 5, "spend": 5, "spent": 5, "income": 5, "expense": 5,
                "balance": 4, "cash": 4, "money": 3, "earnings": 4,
                "afford": 3, "cost": 2, "much": 1}),
]

# Cues that a message is asking how the app works rather than about stored
# figures, so a matching help topic should win over a data tool.
_HOWTO_CUES = ("how do", "how to", "how can", "where do", "where can", "where i",
               "add a", "add an", "set up", "create", "use the", "what is",
               "what does", "how much is a", "track my", "scan", "export",
               "backup", "back up")


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("?", " ").split())


def _is_howto(text: str) -> bool:
    low = _norm(text)
    return any(cue in low for cue in _HOWTO_CUES)


# Casual greetings and pleasantries that carry no data question. A small local
# model misclassifies these constantly (e.g. it routes "hi" to the budget tool),
# so the router answers them itself before any model intent override runs. Match
# only on short messages so a real question starting with one of these words
# ("hey, what am I missing?") still reaches the data tools.
_SMALLTALK_EXACT = {
    "hi", "hey", "hello", "hallo", "helo", "hie", "heya", "yo", "hiya",
    "howdy", "hola", "buna", "sasa", "sup", "hey there", "hi there",
    "good morning", "good afternoon", "good evening", "good day",
    "morning", "afternoon", "evening",
    "whats up", "what up", "wassup", "how are you", "how are you doing",
    "how r u", "hows it going", "how is it going", "how you doing",
    "how do you do", "you good", "you ok", "you okay", "are you ok",
    "are you okay", "hows things", "how are things", "how have you been",
    "how r u doing", "how ru", "not much", "not much you",
    "nice to meet you", "pleasure to meet you", "greetings",
    "thanks", "thank you", "thanks a lot", "thank you so much", "thx",
    "ty", "much appreciated", "appreciate it", "awesome thanks",
    "perfect thanks", "great thanks", "okay thanks", "ok thanks",
    "bye", "goodbye", "see you", "see ya", "cya", "take care",
    "have a good day", "thats all", "nothing else",
}

# Interjection / filler words to strip before the exact match, so "oh hello",
# "hi there" and "yes thanks" all reduce to a known greeting.
_SMALLTALK_FILLER = {"oh", "ah", "ahh", "hmm", "please", "and", "just", "yes",
                     "yep", "ok", "okay", "there", "then", "so", "well"}


def _is_smalltalk(text: str) -> bool:
    """True for a bare greeting/pleasantry with no actual question in it.

    Pure exact match on the curated set: a real data or how-to question never
    reduces to one of these phrases, so we deliberately do NOT consult the
    scoring router here (its substring matching mis-scores short words like
    "hi", which is exactly the artifact that let a greeting reach a data tool).
    """
    low = _norm(text)
    if not low or len(low) > 40:
        return False
    # Drop punctuation and apostrophes, then fillers, before the exact match.
    low = re.sub(r"[^a-z0-9\s]", "", low.replace("'", ""))
    words = [w for w in low.split() if w not in _SMALLTALK_FILLER]
    return " ".join(words) in _SMALLTALK_EXACT


# --- intent routing ---------------------------------------------------------

def _detect_intent(text: str, has_asset: bool) -> str:
    """Score a message against every data concept and return the best intent.

    Returns "help" when nothing clears :data:`_DATA_THRESHOLD`, letting the
    caller decide between app-help and the transparent fallback.
    """
    if has_asset:
        return "image"
    tokens = tokenize(text)
    if not tokens:
        return "help"
    best_intent, best_score = "help", 0
    for intent, terms in _DATA_CONCEPTS:
        s = score(tokens, terms)
        if s > best_score:
            best_intent, best_score = intent, s
    return best_intent if best_score >= _DATA_THRESHOLD else "help"


# --- read-tools -------------------------------------------------------------

def _account_balances(db: Session, user: User) -> tuple[int | None, list[Account]]:
    from app.api.finance import _account_balance

    accounts = db.scalars(select(Account).where(Account.user_id == user.id)).all()
    initialized = [a for a in accounts if a.initialized]
    total = sum(_account_balance(db, a) for a in initialized) if initialized else None
    return total, initialized


def _tool_budget(db: Session, user: User) -> dict:
    today = date.today()
    month_start = today.replace(day=1)

    def month_total(kind: str) -> int:
        return db.scalar(
            select(func.coalesce(func.sum(Transaction.amount_minor), 0)).where(
                Transaction.user_id == user.id,
                Transaction.type == kind,
                Transaction.occurred_on >= month_start,
                Transaction.occurred_on <= today,
            )
        ) or 0

    txn_count = db.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.user_id == user.id,
            Transaction.occurred_on >= month_start,
            Transaction.occurred_on <= today,
        )
    ) or 0
    savings = db.scalar(
        select(func.coalesce(func.sum(GoalContribution.amount_minor), 0)).where(
            GoalContribution.user_id == user.id,
            GoalContribution.occurred_on >= month_start,
            GoalContribution.occurred_on <= today,
        )
    ) or 0
    total_available, _ = _account_balances(db, user)

    card = {
        "kind": "metrics",
        "title": f"This month ({month_start:%b %Y})",
        "items": [
            {"label": "Total available", "minor": total_available,
             "text": None if total_available is not None else "No accounts set up yet",
             "hint": "Across accounts you initialised"},
            {"label": "Income", "minor": month_total("income"), "text": None, "hint": None},
            {"label": "Expenses", "minor": month_total("expense"), "text": None, "hint": None},
            {"label": "Saved toward goals", "minor": savings, "text": None, "hint": None},
        ],
    }
    if txn_count == 0:
        content = (
            "I don't have any transactions recorded for this month yet, so there's "
            "nothing to summarise. Add income or expenses and I can budget from them."
        )
    else:
        content = (
            f"Based on {txn_count} transaction(s) recorded this month, here is your "
            "cash position. Figures come straight from your saved records — I have "
            "not estimated anything that wasn't entered."
        )
    return {"content": content, "cards": [card], "proposal": None}


def _shortage_rows(db: Session, user: User, keyword: str | None):
    items = db.scalars(
        select(InventoryItem).where(
            InventoryItem.user_id == user.id, InventoryItem.deleted_at.is_(None)
        )
    ).all()
    cat_names = {c.id: c.name for c in db.scalars(
        select(InventoryCategory).where(InventoryCategory.user_id == user.id)
    ).all()}

    def matches(item: InventoryItem) -> bool:
        if not keyword:
            return True
        cat = (cat_names.get(item.category_id) or "").lower()
        return keyword in item.name.lower() or keyword in cat

    rows = []
    price_needed = 0
    est_total = 0
    has_unpriced = False
    for item in items:
        if item.target_quantity is None or item.quantity_owned >= item.target_quantity:
            continue
        if not matches(item):
            continue
        need = item.target_quantity - item.quantity_owned
        if item.estimated_unit_cost_minor is None:
            price_needed += 1
            has_unpriced = True
            cost_line = "price needed"
            minor = None
        else:
            cost = need * item.estimated_unit_cost_minor
            est_total += cost
            cost_line = None  # shown via minor
            minor = cost
        rows.append({
            "heading": item.name,
            "sub": cat_names.get(item.category_id),
            "badge": f"need {need}",
            "minor": minor,
            "lines": [cost_line] if cost_line else [],
        })
    return rows, price_needed, est_total, has_unpriced, len(items)


def _tool_shortages(db: Session, user: User, text: str) -> dict:
    # Category nouns in the question are unreliable to match against saved item
    # names, so we list every real shortage rather than risk hiding one.
    rows, price_needed, est_total, has_unpriced, total_items = _shortage_rows(
        db, user, None
    )
    if not rows:
        content = (
            f"I found no items below their target across your {total_items} tracked "
            "item(s). Either you're stocked up, or targets/prices aren't recorded "
            "yet — I won't invent a shortfall."
        )
        return {"content": content, "cards": [], "proposal": None}

    cards = [{
        "kind": "list",
        "title": "Items to restock",
        "rows": rows,
    }]
    total_minor = None if has_unpriced else est_total
    cards.append({
        "kind": "metrics",
        "title": "Restock estimate",
        "items": [
            {"label": "Items below target", "minor": None, "text": str(len(rows)),
             "hint": None},
            {"label": "Need a price entered", "minor": None, "text": str(price_needed),
             "hint": "Not counted in the total"},
            {"label": "Estimated cost to target", "minor": total_minor,
             "text": "Add prices for a full estimate" if total_minor is None else None,
             "hint": "From your saved unit costs only"},
        ],
    })
    tail = (
        " Some items have no price recorded, so the total is not a real figure — "
        "enter prices to complete it."
        if has_unpriced else
        " The total uses your saved unit costs; nothing is guessed."
    )
    content = f"Here's what you're short on. {tail}"
    return {"content": content, "cards": cards, "proposal": None}


def _tool_priority(db: Session, user: User) -> dict:
    goals = db.scalars(
        select(Goal).where(Goal.user_id == user.id, Goal.status == "active")
    ).all()
    if not goals:
        return {
            "content": "You have no active goals, so there's nothing to prioritise "
                       "yet. Create a goal and I'll rank it by deadline and urgency.",
            "cards": [], "proposal": None,
        }
    today = date.today()
    scored = []
    for g in goals:
        saved = db.scalar(
            select(func.coalesce(func.sum(GoalContribution.amount_minor), 0)).where(
                GoalContribution.goal_id == g.id
            )
        ) or 0
        outstanding = None
        if g.type == "money" and g.target_amount_minor is not None:
            outstanding = max(g.target_amount_minor - saved, 0)
        reasons = [f"Priority: {g.priority}"]
        score = _PRIORITY_RANK.get(g.priority, 2)
        if g.deadline:
            days = (g.deadline - today).days
            reasons.append(
                f"due {g.deadline:%b %d} ({days} days out)" if days >= 0
                else f"overdue since {g.deadline:%b %d}"
            )
            score += 4 if days < 0 else max(0, 4 - days // 14)
        if g.type == "quantity":
            reasons.append(
                f"{g.current_quantity or 0}/{g.target_quantity or '?'} collected"
            )
        scored.append((score, g, reasons, outstanding))
    scored.sort(key=lambda s: (-s[0], s[1].deadline or date.max))
    rows = [{
        "heading": f"{i + 1}. {g.name}",
        "sub": g.type,
        "badge": g.priority,
        "minor": outstanding,
        "lines": reasons,
    } for i, (_score, g, reasons, outstanding) in enumerate(scored)]
    return {
        "content": "I ranked your active goals by priority and how close their "
                   "deadlines are, using only what you've recorded. Highest first.",
        "cards": [{"kind": "list", "title": "Suggested focus order", "rows": rows}],
        "proposal": None,
    }


def _tool_obligations(db: Session, user: User) -> dict:
    today = date.today()
    rows = []
    fees = db.scalars(
        select(FeeObligation).where(
            FeeObligation.user_id == user.id, FeeObligation.deleted_at.is_(None)
        )
    ).all()
    for f in fees:
        outstanding = max(f.amount_due_minor - f.amount_paid_minor, 0)
        if outstanding <= 0:
            continue
        badge = "unpaid" if f.amount_paid_minor == 0 else "partial"
        when = f"due {f.due_on:%b %d}" if f.due_on else "no due date set"
        rows.append({
            "heading": f.name, "sub": f.category, "badge": badge,
            "minor": outstanding, "lines": [when],
        })
    goals = db.scalars(
        select(Goal).where(
            Goal.user_id == user.id, Goal.status == "active", Goal.deadline.isnot(None)
        )
    ).all()
    for g in goals:
        if g.deadline < today:
            badge = "overdue"
        elif (g.deadline - today).days <= 30:
            badge = "soon"
        else:
            badge = "planned"
        rows.append({
            "heading": g.name, "sub": "goal deadline", "badge": badge,
            "minor": None, "lines": [f"due {g.deadline:%b %d}"],
        })
    if not rows:
        return {
            "content": "No outstanding fees or upcoming goal deadlines in your "
                       "records right now. I only report what's saved, so nothing "
                       "is marked paid that isn't.",
            "cards": [], "proposal": None,
        }
    rows.sort(key=lambda r: 0 if r["badge"] in ("unpaid", "overdue", "partial", "soon") else 1)
    return {
        "content": "These are your open obligations from saved fee and goal records. "
                   "A fee shows as paid only when a payment is actually recorded.",
        "cards": [{"kind": "list", "title": "Upcoming obligations", "rows": rows}],
        "proposal": None,
    }


def _tool_tasks(db: Session, user: User) -> dict:
    goals = db.scalars(
        select(Goal).where(Goal.user_id == user.id, Goal.status == "active")
    ).all()
    if not goals:
        return {
            "content": "There are no active goals to turn into tasks yet. Add a "
                       "goal and I can draft weekly tasks from it (as a proposal "
                       "for you to approve).",
            "cards": [], "proposal": None,
        }
    week_from_now = date.today().fromordinal(date.today().toordinal() + 7)
    items = [{
        "title": f"Work toward: {g.name}",
        "goal_id": g.id,
        "priority": g.priority,
        "due_on": week_from_now.isoformat(),
    } for g in goals]
    proposal = {
        "kind": "create_tasks_from_goals",
        "title": f"Create {len(items)} proposed task(s) from your active goals",
        "payload": {"tasks": items},
    }
    rows = [{
        "heading": it["title"], "sub": None, "badge": it["priority"],
        "minor": None, "lines": [f"proposed due {it['due_on']}"],
    } for it in items]
    return {
        "content": "I drafted one weekly task per active goal. These are proposals "
                   "only — nothing is added to your tasks until you confirm below.",
        "cards": [{"kind": "list", "title": "Proposed tasks", "rows": rows}],
        "proposal": proposal,
    }


def _tool_image(db: Session, user: User, asset_id: str) -> dict:
    # Assets are a shared, user-agnostic library (ids are opaque, not paths);
    # analysis only reads category metadata, never invents a price.
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    root = _assets_root()
    result = analyze_image(root / asset.rel_path, asset.category) or {}
    category = result.get("predicted_category") or asset.category
    item_type = result.get("predicted_item_type") or category.rsplit("/", 1)[-1]
    confidence = result.get("confidence")
    source = result.get("source", "folder")
    uncertain = (confidence is None or confidence < 0.75) or source == "folder"

    cards = [{
        "kind": "metrics",
        "title": "Image analysis",
        "items": [
            {"label": "Likely category", "minor": None, "text": category, "hint": None},
            {"label": "Suggested item", "minor": None, "text": item_type, "hint": None},
            {"label": "Confidence", "minor": None,
             "text": (f"{confidence:.0%}" if isinstance(confidence, (int, float)) else "unknown"),
             "hint": "From folder placement" if source == "folder" else None},
        ],
    }]
    caveat = (
        " I classified this from the folder it's stored in, not from the pixels — "
        "so treat it as a suggestion and correct it if it's wrong. I never infer a "
        "price or seller from a photo."
        if source == "folder" else
        " I never infer a price or seller from a photo."
    )
    content = (
        f"This looks like a {item_type} ({category}).{caveat}"
        if uncertain else
        f"This is a {item_type} in {category}.{caveat}"
    )
    proposal = {
        "kind": "add_inventory_item",
        "title": f"Add “{item_type.replace('_', ' ')}” to inventory",
        "payload": {
            "name": item_type.replace("_", " ").strip().title(),
            "category": category.split("/", 1)[0],
            "quantity": 0,
            "estimated_unit_cost_minor": None,
            "image_asset_id": asset.id,
        },
    }
    return {"content": content, "cards": cards, "proposal": proposal}


def _tool_apphelp(topic: assistant_help.HelpTopic) -> dict:
    return {
        "content": f"{topic.answer} You do this on {topic.screen}.",
        "cards": [],
        "proposal": None,
    }


def _tool_help(user: User) -> dict:
    return {
        "content": assistant_help.UNKNOWN_GUIDANCE,
        "cards": [],
        "proposal": None,
    }


def _tool_greeting() -> dict:
    """A warm, honest opener for casual greetings so a bare "hi" (or a small
    model misreading one) never dumps a data report on the user."""
    return {
        "content": (
            "Hey there. I'm your LifeSmart assistant. I answer only from your "
            "own saved records — your money and budget, what you're low on, your "
            "goals and their priority, fees and deadlines — and I can explain how "
            "to use the app. Anything I'd change waits for you to confirm it. What "
            "would you like to look at?"
        ),
        "cards": [],
        "proposal": None,
    }


# --- retrieval over the project (help + the user's own records) -------------
#
# When the deterministic router has no confident answer, we assemble a short,
# grounded block of "reference notes" for the optional local model: the closest
# app-help topics (searched even when they score below the match threshold) plus
# a live summary of the user's saved figures. Every number in here comes from
# the database, so the model can only restate what LifeSmart already knows.

def _major(minor: int | None) -> str:
    return "not recorded" if minor is None else str(int(round(minor / 100)))


def _help_notes(text: str) -> list[str]:
    tokens = tokenize(text)
    if not tokens:
        return []
    ranked = sorted(
        assistant_help.TOPICS,
        key=lambda t: score(tokens, t.terms),
        reverse=True,
    )
    return [f"{t.title}: {t.answer}" for t in ranked[:2]
            if score(tokens, t.terms) > 0]


def _data_notes(db: Session, user: User) -> list[str]:
    today = date.today()
    month_start = today.replace(day=1)
    notes: list[str] = []

    total, initialized = _account_balances(db, user)
    notes.append(
        f"Money: {len(initialized)} account(s) initialised, about "
        f"{_major(total)} KES available across them."
    )

    def month_total(kind: str) -> int:
        return db.scalar(
            select(func.coalesce(func.sum(Transaction.amount_minor), 0)).where(
                Transaction.user_id == user.id,
                Transaction.type == kind,
                Transaction.occurred_on >= month_start,
                Transaction.occurred_on <= today,
            )
        ) or 0

    notes.append(
        f"This month so far: about {_major(month_total('income'))} KES income and "
        f"{_major(month_total('expense'))} KES in expenses."
    )

    goals = db.scalars(
        select(Goal).where(Goal.user_id == user.id, Goal.status == "active")
    ).all()
    if goals:
        listing = "; ".join(f"{g.name} (priority {g.priority})" for g in goals[:6])
        notes.append(f"Active goals ({len(goals)}): {listing}.")
    else:
        notes.append("Active goals: none recorded yet.")

    _rows, _pn, _est, _up, total_items = _shortage_rows(db, user, None)
    notes.append(
        f"Inventory: {total_items} item(s) tracked, {len(_rows)} below their "
        f"target."
    )

    fees = db.scalars(
        select(FeeObligation).where(
            FeeObligation.user_id == user.id, FeeObligation.deleted_at.is_(None)
        )
    ).all()
    open_fees = sum(1 for f in fees if (f.amount_due_minor - f.amount_paid_minor) > 0)
    notes.append(f"Fee obligations still owing: {open_fees}.")
    return notes


def _build_context(db: Session, user: User, text: str) -> str:
    parts: list[str] = ["Application help:"]
    parts += [f"- {n}" for n in _help_notes(text)] or ["- (none matched)"]
    parts.append("The user's saved records (approximate, today):")
    parts += [f"- {n}" for n in _data_notes(db, user)]
    return "\n".join(parts)


def _model_assisted(db: Session, user: User, text: str) -> dict | None:
    """Let a loaded model answer from retrieved project context, or None.

    None means 'no model ready' or 'the answer broke the honesty guard', in
    which case the caller keeps the deterministic guidance fallback.
    """
    if not llm.is_ready():
        return None
    context = _build_context(db, user, text)
    ans = llm.answer(context, text)
    if not ans:
        return None
    return {"content": ans, "cards": [], "proposal": None}


# --- helpers ----------------------------------------------------------------

def _assets_root() -> Path:
    from app.core.config import get_settings

    return get_settings().assets_root_path


def _run_tool(db: Session, user: User, text: str, intent: str) -> dict:
    if intent == "tasks":
        return _tool_tasks(db, user)
    if intent == "priority":
        return _tool_priority(db, user)
    if intent == "obligations":
        return _tool_obligations(db, user)
    if intent == "shortages":
        return _tool_shortages(db, user, text)
    if intent == "budget":
        return _tool_budget(db, user)
    return _tool_help(user)


def respond(db: Session, user: User, text: str, asset_id: str | None) -> dict:
    """Answer a turn, grounded on saved records and the built-in help.

    Image turns go straight to the image tool. Otherwise the message is scored
    against the data concepts and the app-help knowledge base: an explicit
    "how do I use the app" question prefers a help topic, a data question runs
    its read-tool, and anything unclear falls back to a transparent guide.

    When the user has loaded the optional local model it strengthens this flow
    without ever owning a figure: it may pick a more accurate data intent and
    reword a read-tool's summary (rejected if it introduces a new number), and
    it answers genuinely unmatched questions from retrieved project context
    (help topics + the user's own records). If no model is loaded, or an answer
    fails the honesty guard, the deterministic router answers - so every figure
    still comes only from the grounded read-tools and nothing is fabricated.
    """
    if asset_id is not None:
        return _tool_image(db, user, asset_id)

    # A bare greeting is answered directly, before any model intent override, so
    # a misread "hi" can never open a budget/inventory report.
    if _is_smalltalk(text):
        return _tool_greeting()

    intent = _detect_intent(text, False)
    model_ready = llm.is_ready()
    if model_ready:
        chosen = llm.classify_intent(text)
        if chosen and chosen != "help":
            intent = chosen
    topic = assistant_help.match(text)

    if _is_howto(text) and topic is not None:
        return _tool_apphelp(topic)
    if intent != "help":
        result = _run_tool(db, user, text, intent)
        if model_ready:
            reworded = llm.rephrase(result["content"])
            if reworded:
                result = {**result, "content": reworded}
        return result
    if topic is not None:
        return _tool_apphelp(topic)
    assisted = _model_assisted(db, user, text)
    if assisted is not None:
        return assisted
    return _tool_help(user)
