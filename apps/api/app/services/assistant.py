"""Grounded assistant over validated read-tools.

Routing is deterministic by default (a transparent keyword router). When the
user has loaded a local Qwen model (see app.services.llm) it may refine the
intent classification and reword the summary prose, but it never produces the
figures. The model is opt-in per session and is never loaded on its own.
Every number reported is computed from the user's own saved records; unknown
values stay unknown; and any change it wants to make is returned as a *proposal*
that only persists after the user confirms it. It never writes financial
records, never infers a price or seller from a photograph, and never fabricates
data.
"""
from __future__ import annotations

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
from app.services.analysis import analyze_image

# Priority ordering for goal ranking (higher = more urgent).
_PRIORITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("?", " ").split())


# --- intent routing ---------------------------------------------------------

def _detect_intent(text: str, has_asset: bool) -> str:
    if has_asset:
        return "image"
    t = _norm(text)
    if any(k in t for k in ("task", "to do", "todo", "schedule", "plan my week",
                            "turn my goals", "weekly plan", "reminders")):
        return "tasks"
    if any(k in t for k in ("priorit", "which goal", "rank", "focus", "order my goals",
                            "what should i do")):
        return "priority"
    if any(k in t for k in ("fee", "fees", "obligation", "due", "deadline",
                            "upcoming", "when do i", "semester fees")):
        return "obligations"
    if any(k in t for k in ("missing", "shortage", "run out", "need to buy",
                            "what do i need", "wardrobe", "stock", "low on",
                            "affordable", "complete my", "cost to", "restock")):
        return "shortages"
    if any(k in t for k in ("budget", "spend", "spent", "income", "expense",
                            "balance", "cash", "money", "afford", "earnings",
                            "how much")):
        return "budget"
    return "help"


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


def _tool_help(user: User) -> dict:
    return {
        "content": (
            "I answer from your saved records only — I don't guess or invent data. "
            "Try: “What am I missing in my wardrobe?”, “Help me budget for next "
            "semester.”, “Which goals should I prioritize?”, “What fees are due?”, "
            "“Turn my goals into weekly tasks.”, or attach a product image to "
            "classify it. Anything I'd change is shown as a proposal you confirm "
            "first."
        ),
        "cards": [],
        "proposal": None,
    }


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
    """Answer a turn.

    Routing prefers the local LLM's intent classification only while the user
    has loaded it from the AI page, and otherwise falls back to the
    deterministic keyword detector; image turns always go straight to the image
    tool. Every figure comes from the grounded tools below; the LLM may only
    reword the summary prose (and never add a number), so enabling it cannot
    fabricate data or bypass permissions.
    """
    from app.services import llm

    if asset_id is not None:
        return _tool_image(db, user, asset_id)

    intent = llm.classify_intent(text) or _detect_intent(text, False)
    result = _run_tool(db, user, text, intent)

    polished = llm.rephrase(result["content"])
    if polished:
        result["content"] = polished
    return result
