"""On-device natural-language helpers for the assistant.

This module carries the small, dependency-free text engine the assistant runs
on: normalise -> drop stopwords -> light suffix stem -> token set, plus a
weighted term scorer. The same primitives drive both the data-intent router in
:mod:`app.services.assistant` and the app-help knowledge base below, so a
question phrased a hundred different ways still maps to one answer.

The app-help part is deliberately honest: every topic describes a feature that
really exists in this build (mirrors the Settings "integrations" surface) and
points at the screen it lives on. Nothing here fabricates a figure or promises
a connection LifeSmart does not have - it only explains how the app works.
"""
from __future__ import annotations

import re

# Common English filler words. Dropping them lets the scorer focus on the
# content words that actually carry intent, so "how do I add an expense?" and
# "add expense" score the same.
STOPWORDS = frozenset(
    """a an and are as at be but by can do does for from has have how i if in
    is it me my of on or please should the this that to was we what when where
    which who why will with you your im i'm id""".split()
)

_WORD_RE = re.compile(r"[a-z0-9']+")


def stem(word: str) -> str:
    """Very light, deterministic suffix stripper.

    Not a real Porter stemmer - just enough to collapse the plural/verb forms
    that show up in short questions ("expenses"->"expense", "running"->"run",
    "goals"->"goal", "due"->"due"). Keeps a stable minimum length so short
    words are left intact.
    """
    w = word
    for suffix in ("ies", "es", "s"):
        if len(w) > 4 and w.endswith(suffix):
            w = w[: -len(suffix)] + ("y" if suffix == "ies" else "")
            break
    else:
        if len(w) > 5 and w.endswith("ing"):
            w = w[:-3]
        elif len(w) > 4 and w.endswith("ed"):
            w = w[:-2]
    return w.rstrip("_")


def tokenize(text: str) -> set[str]:
    """Lowercase, strip punctuation, drop stopwords, stem - as a token set."""
    raw = _WORD_RE.findall((text or "").lower())
    return {stem(w) for w in raw if w not in STOPWORDS and len(w) > 1}


def score(tokens: set[str], terms: dict[str, int]) -> int:
    """Weighted overlap between a message's tokens and a term table.

    A term matches if a message token equals it or one contains the other
    (bounded so "goal" doesn't accidentally match "go"), giving partial-phrase
    credit without a full parser.
    """
    total = 0
    for term, weight in terms.items():
        s = stem(term.lower())
        for t in tokens:
            if t == s or (len(s) > 3 and (s in t or t in s)) or (
                len(s) <= 3 and t == s
            ):
                total += weight
                break
    return total


class HelpTopic:
    """One 'how do I use the app' answer the matcher can surface."""

    __slots__ = ("id", "terms", "title", "answer", "screen")

    def __init__(self, id: str, terms: dict[str, int], title: str,
                 answer: str, screen: str) -> None:
        self.id = id
        self.terms = terms
        self.title = title
        self.answer = answer
        self.screen = screen


def _topic(id, terms, title, answer, screen) -> HelpTopic:
    return HelpTopic(id, terms, title, answer, screen)


# The knowledge base. Order only matters for tie-breaking (earlier wins), so
# put the more specific topics first. Each `terms` dict is a weighted concept
# list; the scorer adds up every term that overlaps the message.
TOPICS: list[HelpTopic] = [
    _topic(
        "assistant",
        {"assistant": 4, "chat": 3, "ai": 3, "bot": 3, "help": 2,
         "ask": 2, "answer": 2, "prompts": 2},
        "Using the AI Assistant",
        "The assistant is a plain-language chat over your own LifeSmart data. "
        "Ask it about your money, goals, inventory or deadlines and it answers "
        "straight from your saved records - it never invents a figure. Ask it "
        "how to do something and it explains the screen to use. If it wants to "
        "change anything (a task, an inventory item) it shows a proposal you "
        "confirm first. Attach a product image and it will suggest a category. "
        "Everything runs on this machine.",
        "Assistant (this page)",
    ),
    _topic(
        "add_transaction",
        {"expense": 4, "income": 4, "transaction": 4, "money": 3, "spend": 3,
         "spent": 3, "earn": 3, "record": 3, "add": 2, "categorise": 2,
         "categorize": 2, "cost": 2, "purchase": 2},
        "Adding income and expenses",
        "Open Money, pick or create an account, then add a transaction: choose "
        "income or expense, type the amount and a category (food, rent, "
        "allowance, transport...), and the date. Money you record here is what "
        "the assistant and your reports use - nothing is fetched from a bank or "
        "M-PESA automatically.",
        "Money (/app/money)",
    ),
    _topic(
        "account_balance",
        {"account": 3, "balance": 4, "cash": 3, "mpesa": 3, "bank": 3,
         "wallet": 3, "initialise": 4, "initialize": 4, "start": 2,
         "starting": 2},
        "Setting up an account and its balance",
        "In Money, add an account (cash, M-PESA, bank or other). To give it a "
        "starting figure, initialise it with a balance - until you do, its "
        "balance stays unknown rather than showing a false zero. You can note "
        "the phone number an M-PESA account is on or a bank account number; "
        "these are your own notes and link to nothing.",
        "Money (/app/money)",
    ),
    _topic(
        "goal",
        {"goal": 4, "save": 3, "saving": 3, "target": 3, "fund": 3,
         "contribution": 3, "milestone": 2, "progress": 2},
        "Creating and tracking a goal",
        "On Goals, add a goal: a name, whether it is a money target or a "
        "quantity (like collecting items), a target amount, a priority and an "
        "optional deadline. Log contributions toward it and LifeSmart shows how "
        "much is saved and how much is outstanding. Money goals never guess a "
        "number - outstanding is target minus what you actually recorded.",
        "Goals (/app/goals)",
    ),
    _topic(
        "fee",
        {"fee": 5, "fees": 5, "tuition": 4, "obligation": 4, "due": 3,
         "semester": 3, "school": 3, "course": 2, "pay": 2, "payment": 2,
         "outstanding": 2, "student": 3},
        "Tracking fees and obligations",
        "On the Student page, add a fee obligation with its amount due, a "
        "category (tuition, hostel, exam...) and a due date, then log partial "
        "payments. The outstanding balance is what is left after your recorded "
        "payments - a fee only shows as paid once you record the full payment. "
        "The assistant lists what is due under its obligations answer.",
        "Student (/app/student)",
    ),
    _topic(
        "inventory",
        {"inventory": 4, "item": 3, "stock": 3, "owned": 3, "quantity": 3,
         "wardrobe": 4, "missing": 3, "short": 3, "restock": 3, "belongings": 3,
         "own": 2},
        "Tracking what you own and what you're missing",
        "On Inventory, keep a list of your belongings with a category, how many "
        "you own and (optionally) a target quantity and estimated unit cost. "
        "Anything below its target counts as a shortage; the Shopping page and "
        "the assistant add up what you're missing and, if you entered prices, "
        "an estimated cost. Prices are only ever what you recorded.",
        "Inventory (/app/inventory)",
    ),
    _topic(
        "shopping",
        {"shop": 4, "shopping": 4, "buy": 3, "buying": 3, "afford": 3,
         "wishlist": 2, "purchase": 2, "cheap": 2, "price": 2, "estimate": 2},
        "Using the Shopping list",
        "The Shopping page turns your inventory shortages into a to-buy list "
        "with estimated costs, so you can plan purchases against your budget. "
        "It works from your saved targets, owned quantities and unit costs "
        "only - it never fetches live prices or finds a seller.",
        "Shopping (/app/shopping)",
    ),
    _topic(
        "images",
        {"image": 4, "photo": 4, "picture": 4, "scan": 4, "upload": 3,
         "classify": 3, "categorise": 3, "categorize": 3, "camera": 2,
         "thumbnail": 2},
        "Adding and organising images",
        "On Images, drop photos into the category folders (clothing, household, "
        "electronics...) or upload them. LifeSmart reads the file type and "
        "matches duplicates by hash, and the category is the folder you put it "
        "in - there is no vision model, so it never guesses a brand, item or "
        "price from a photo. Fix a wrong category yourself and it sticks.",
        "Images (/app/images)",
    ),
    _topic(
        "earnings",
        {"earning": 4, "earnings": 4, "income": 3, "saving": 4, "savings": 4,
         "allowance": 3, "stipend": 3, "hustle": 2, "money": 2},
        "Earnings and savings",
        "The Earnings & Savings page summarises the income you've recorded and "
        "what you've set toward goals, so you can see earning trends and saving "
        "progress in one place. Every figure is a roll-up of transactions and "
        "contributions you entered - nothing is estimated.",
        "Earnings (/app/earnings-savings)",
    ),
    _topic(
        "task",
        {"task": 5, "todo": 4, "to-do": 4, "reminder": 4, "schedule": 3,
         "plan": 3, "due": 2, "checklist": 2},
        "Managing tasks and reminders",
        "On Tasks, add your own to-dos with a due date and priority, and tick "
        "them off. The assistant can also draft a weekly task per active goal - "
        "but only as a proposal that becomes a real task when you confirm it. "
        "Reminders appear inside the app; nothing is emailed or texted.",
        "Tasks (/app/tasks)",
    ),
    _topic(
        "networth",
        {"net": 3, "worth": 3, "networth": 4, "asset": 3, "wealth": 2,
         "total": 2, "position": 2},
        "Understanding your net worth",
        "The Net Worth page adds up your account balances and the recorded "
        "value of your belongings to show your overall position. Uninitialised "
        "accounts and unpriced items stay unknown, so the total only ever "
        "reflects figures you actually entered.",
        "Net Worth (/app/networth)",
    ),
    _topic(
        "reports",
        {"report": 5, "summary": 3, "statement": 3, "trend": 3, "overview": 2,
         "spending": 3, "dashboard": 3, "cashflow": 3, "cash": 2, "flow": 2},
        "Reading reports and the dashboard",
        "Reports give cash-flow, spending-by-category and goal-progress "
        "summaries over a period you choose; the Dashboard is your at-a-glance "
        "home view. Both are computed live from your saved records - filter by "
        "account or date range and the numbers re-derive, never guessing for "
        "gaps.",
        "Reports (/app/reports)",
    ),
    _topic(
        "notifications",
        {"notification": 5, "reminder": 4, "alert": 4, "quiet": 3,
         "nudge": 3, "mute": 2},
        "Notifications and reminders",
        "On the Notifications page you choose which in-app reminders you get - "
        "goal nudges, fee-due alerts and so on - and a quiet window. These "
        "reminders show inside LifeSmart only; there is no email, SMS or push "
        "provider connected, so nothing is sent to your phone or inbox.",
        "Notifications (/app/notifications)",
    ),
    _topic(
        "settings",
        {"setting": 5, "settings": 5, "profile": 4, "currency": 4, "name": 2,
         "email": 2, "preferences": 3, "password": 2},
        "Adjusting settings and your profile",
        "Settings holds your profile (name, currency, student status), a full "
        "list of what this build can and cannot connect to, and your data "
        "controls. You can change your display name and currency but not your "
        "sign-in email. Money is stored in exact minor units, so switching "
        "currency only changes how amounts are shown.",
        "Settings (/app/settings)",
    ),
    _topic(
        "export_backup",
        {"export": 5, "backup": 5, "download": 4, "restore": 4, "import": 3,
         "copy": 3, "zip": 2, "json": 2, "csv": 2, "data": 2},
        "Exporting and backing up your data",
        "On Settings, Your data lets you download a zip built on this machine: "
        "a data.json with every row you own (nulls kept), a CSV per table, a "
        "manifest naming the money columns and a README. The same file restores "
        "back, so an export is a real backup. Your data is a single SQLite file "
        "plus the images folder - nothing leaves the device unless you take it "
        "off yourself.",
        "Settings > Your data (/app/settings)",
    ),
    _topic(
        "privacy",
        {"privacy": 5, "private": 3, "secure": 3, "data": 3, "storage": 3,
         "sync": 3, "server": 3, "analytics": 2, "shared": 2, "local": 4,
         "cloud": 3},
        "Your privacy and where data lives",
        "Everything you enter is stored in one database file on this machine. "
        "There is no analytics, no crash reporting and no server sync - "
        "LifeSmart sends your records nowhere. A password, token or file path "
        "never appears in an export. In the desktop app your sign-in identity "
        "is a fixed machine address, not a real email.",
        "Settings (/app/settings)",
    ),
    _topic(
        "sign_in",
        {"login": 4, "log": 2, "signin": 4, "sign": 2, "google": 4,
         "register": 4, "account": 2, "password": 3, "auth": 3, "email": 3},
        "Signing in and accounts",
        "You register with an email and password, or (when configured) sign in "
        "with Google. In the packaged desktop app the single local account is "
        "signed in automatically, so there is no password to remember. Either "
        "way your records stay on this machine; a Google sign-in only creates "
        "the local account, it syncs nothing.",
        "Login (/login)",
    ),
]

# A short, always-honest fallback the router returns when neither a data intent
# nor a help topic matches, so the assistant explains what it can do instead of
# dead-ending.
UNKNOWN_GUIDANCE = (
    "I answer two kinds of questions from what LifeSmart already knows. One: "
    "about your own data - money and budget, what you're missing, your goals "
    "and their priority, fees and deadlines, and turning goals into tasks. "
    "Two: how to use the app - adding an expense, setting up an account, "
    "tracking a goal or fee, organising images, exporting your data, and more. "
    "Try rephrasing with one of those words, or pick a suggested prompt below. "
    "I only ever reply from your saved records and built-in help, and I never "
    "invent a figure."
)


def match(text: str, threshold: int = 5) -> HelpTopic | None:
    """Return the best-matching help topic for a message, or None.

    Scores every topic by weighted term overlap and keeps the highest only if
    it clears ``threshold``; a low score means the question is really about the
    user's data (or unclear) and the caller should fall back elsewhere.
    """
    tokens = tokenize(text)
    if not tokens:
        return None
    best: HelpTopic | None = None
    best_score = 0
    for topic in TOPICS:
        s = score(tokens, topic.terms)
        if s > best_score:
            best, best_score = topic, s
    return best if best_score >= threshold else None
