"""Account-level operations: what is stored where, and how to empty it.

Two honesty rules drive this module.

1. An export is the database, not a report. Column names stay as they are
   stored (integer minor units for money) and a missing value stays null in
   JSON / empty in CSV. Nothing here rounds an unknown to zero, because a
   spreadsheet cannot tell "free" from "never recorded" afterwards.
2. A factory reset is scoped to one account. The picture index (assets,
   asset_analyses) describes image files and is shared machine-wide, so it is
   never deleted and never exported - on a hosted deployment that table holds
   other people's images too. Your image files are always left untouched.

SQLite does not enforce foreign keys here (no PRAGMA foreign_keys in
core/database.py), so a wrongly ordered delete would silently leave orphan
rows instead of failing. The table list below is deliberately ordered
children first for that reason.
"""
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.assistant import Conversation, Message, ProposedAction
from app.models.earnings import BusinessRecord, IncomeSource
from app.models.finance import Account, Transaction
from app.models.goal import Goal, GoalContribution
from app.models.inventory import InventoryCategory, InventoryItem, QuantityEvent
from app.models.notifications import NotificationPreference
from app.models.shopping import PurchaseRecord, ShoppingItem, ShoppingList
from app.models.student import (
    FeeObligation,
    FeePayment,
    FoodBudget,
    HostelOption,
)
from app.models.tasks import Task
from app.models.user import User
from app.models.valuation import NetWorthSnapshot
from app.services import valuation as valuation_service

# Categories a new account starts with. Kept here so sign-up, the local
# bootstrap and a factory reset all seed exactly the same list.
DEFAULT_CATEGORIES = [
    "Clothing",
    "Household",
    "Electronics",
    "Food",
    "Study materials",
    "Personal care",
    "Transport",
]

# Every table one account owns, children before parents. This single list is
# used for the export, for the "what is stored" counts and for the reset, so
# the three can never disagree about what belongs to you.
OWNED_TABLES: list[tuple[type, str, str]] = [
    (ProposedAction, "assistant_proposed_actions", "Assistant proposals"),
    (Message, "assistant_messages", "Assistant messages"),
    (Conversation, "assistant_conversations", "Assistant conversations"),
    (QuantityEvent, "quantity_events", "Quantity changes"),
    (PurchaseRecord, "purchase_records", "Purchases"),
    (ShoppingItem, "shopping_items", "Shopping list items"),
    (ShoppingList, "shopping_lists", "Shopping lists"),
    (GoalContribution, "goal_contributions", "Savings contributions"),
    (FeePayment, "fee_payments", "Fee payments"),
    (Task, "tasks", "Tasks and reminders"),
    (BusinessRecord, "business_records", "Business records"),
    (Transaction, "transactions", "Transactions"),
    (FeeObligation, "fee_obligations", "Fee obligations"),
    (HostelOption, "hostel_options", "Accommodation options"),
    (FoodBudget, "food_budgets", "Food budgets"),
    (Goal, "goals", "Goals"),
    (InventoryItem, "inventory_items", "Inventory items"),
    (InventoryCategory, "inventory_categories", "Inventory categories"),
    (Account, "accounts", "Accounts"),
    (IncomeSource, "income_sources", "Income sources"),
    (NetWorthSnapshot, "net_worth_snapshots", "Net worth snapshots"),
    (NotificationPreference, "notification_preferences", "Notification preferences"),
]

# Names this module deliberately leaves alone, for the privacy note.
NOT_EXPORTED = [
    {
        "key": "assets",
        "label": "Picture index",
        "reason": (
            "Describes image files on this machine and is shared by every "
            "account, so it is neither exported nor deleted. The images "
            "themselves are yours and stay exactly where you put them."
        ),
    },
    {
        "key": "asset_analyses",
        "label": "Picture classification records",
        "reason": (
            "Attached to the picture index rather than to your account, so it "
            "is left in place too. Re-scanning rebuilds them."
        ),
    },
]


def seed_default_categories(db: Session, user: User) -> None:
    """Add the starter categories without committing (callers own the tx)."""
    for name in DEFAULT_CATEGORIES:
        db.add(InventoryCategory(user_id=user.id, name=name))


def storage_counts(db: Session, user: User) -> list[dict]:
    """Row counts per owned table - the 'what is stored about me' list."""
    out: list[dict] = []
    for model, key, label in OWNED_TABLES:
        rows = db.scalar(
            select(func.count()).select_from(model).where(model.user_id == user.id)
        )
        out.append({"key": key, "label": label, "rows": int(rows or 0)})
    return out


def total_rows(counts: list[dict]) -> int:
    return sum(c["rows"] for c in counts)


def reset(db: Session, user: User) -> dict:
    """Delete every record this account owns; keep the account itself.

    On the desktop app the sign-in identity is recreated on the next launch,
    so removing the user row would only produce a blank profile you cannot
    return from. Keeping it means the app still opens, to an empty life.
    Returns what was removed so the caller can report it honestly.
    """
    db.flush()
    deleted: dict[str, int] = {}
    for model, key, _label in OWNED_TABLES:
        result = db.execute(
            delete(model).where(model.user_id == user.id)
        )
        deleted[key] = int(result.rowcount or 0)

    # A fresh account gets the starter categories back, otherwise the
    # Inventory page has nowhere to put the first item.
    seed_default_categories(db, user)
    # The saved net worth must agree with the now-empty inventory rather than
    # keep showing the figure from before the reset.
    valuation_service.record(db, user)
    db.commit()
    return {
        "deleted": deleted,
        "deleted_total": sum(deleted.values()),
        "kept": ["account sign-in", "profile details", "picture index",
                 "your image files on disk"],
        "reseeded": DEFAULT_CATEGORIES,
    }
