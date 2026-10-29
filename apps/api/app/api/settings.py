"""Settings API: one read that answers profile, preferences, integrations and
privacy at the same time.

The integration list is the product's honesty surface. Every capability states
whether it works now, only runs when you start it, is something you do by hand,
is switched off, or simply does not exist in this product - so nothing on the
screen implies a connection LifeSmart does not have.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api import notifications
from app.core.config import Settings, data_home, get_settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.settings import SettingsOut
from app.services import account as account_service
from app.services import llm

router = APIRouter(prefix="/api/settings", tags=["settings"])

PRIVACY_STATEMENT = [
    "Everything you enter is stored in one database file on this machine. "
    "LifeSmart sends your records nowhere.",
    "This build has no analytics, no crash reporting and no server sync.",
    "Money is kept in integer minor units so totals are exact. A value you "
    "never entered stays null - it is never shown or exported as zero.",
    "A data export contains no password, no token and no file-system path.",
    "An M-PESA number or bank account number you typed is kept with the account "
    "and appears in an export. It is your own note about your account: no "
    "connection reads it, and nothing verifies it.",
    "In local desktop mode the sign-in identity is a fixed machine address, "
    "not a real email address, and it cannot be changed.",
]

EXPORT_NOTE = (
    "The download is a zip built on this machine: data.json with every row you "
    "own (nulls kept), one CSV per table, manifest.json naming the money "
    "columns, and a README. Nothing is uploaded to produce it. The same file "
    "can be put back with the restore below, so a downloaded export is a backup "
    "and not only a copy."
)


def _assistant_integration() -> dict:
    return {
        "key": "assistant", "label": "AI Assistant",
        "status": "available",
        "detail": (
            "The assistant runs entirely on this machine with a deterministic, "
            "on-device language router, so it works on any device even with no "
            "model loaded. It answers from your saved records and from built-in "
            "help about how to use the app, never invents a figure, and sends "
            "nothing anywhere. Any change it suggests is a proposal you confirm "
            "before it writes."
        ),
        "action": "AI Assistant",
    }


def _size_text(size_mb: float | None) -> str:
    return f" ({size_mb:.0f} MB)" if size_mb else ""


def _model_integration(st: dict) -> dict:
    """Map the optional model lifecycle onto an honest status label."""
    name = st["model_file"] or "no model file"
    state = st["state"]
    if state == "ready":
        return {
            "key": "local_model", "label": "On-device AI model",
            "status": "available",
            "detail": (
                f"{name}{_size_text(st['size_mb'])} is loaded and helping on "
                "the AI page: it can reword a summary and answer questions the "
                "router does not cover, but only from your own saved records and "
                "built-in help - an answer that introduces a new figure is "
                "rejected, and it cannot write to your records."
            ),
            "action": "AI Assistant > Unload model",
        }
    if state == "loading":
        return {
            "key": "local_model", "label": "On-device AI model",
            "status": "on_demand",
            "detail": f"{name} is loading now. Nothing loads at startup.",
            "action": "AI Assistant",
        }
    if st["available"]:
        return {
            "key": "local_model", "label": "On-device AI model",
            "status": "on_demand",
            "detail": (
                f"{name}{_size_text(st['size_mb'])} is on this machine but not "
                "in memory. Press Load when you want it to help answer; Unload "
                "frees the RAM again. The assistant works fully without it."
            ),
            "action": "AI Assistant > Load model",
        }
    reason = llm.unavailable_reason() or "no model available"
    return {
        "key": "local_model", "label": "On-device AI model",
        "status": "unavailable",
        "detail": (
            f"No on-device model is running here: {reason}. The assistant "
            "answers with its own deterministic routing, which never invents "
            "data."
        ),
        "action": ".env: ASSISTANT_LLM_ENABLED",
    }


def integrations(settings: Settings) -> list[dict]:
    st = llm.status()
    google = {
        "key": "google_signin", "label": "Google sign-in",
        "detail": "", "status": "not_configured", "action": None,
    }
    if settings.google_client_id:
        google["status"] = "available"
        google["detail"] = (
            "A Google client is configured, so an account can be created from "
            "a Google sign-in. Your records still stay on this machine."
        )
    elif settings.local_single_user:
        google["detail"] = (
            "Not used here. The desktop app signs this one account in "
            "automatically, so there is no password to remember or reset."
        )
    else:
        google["detail"] = (
            "No Google client is configured. Sign in with the email and "
            "password you registered, or set GOOGLE_CLIENT_ID to enable it."
        )
        google["action"] = ".env: GOOGLE_CLIENT_ID"

    return [
        _assistant_integration(),
        _model_integration(st),
        google,
        {
            "key": "image_classification", "label": "Picture classification",
            "status": "manual",
            "detail": (
                "The category is the folder you put an image in; the file's "
                "real type is detected from its contents, and duplicates are "
                "matched by hash. No vision model is connected, so LifeSmart "
                "never guesses an item, a brand or a price from a photograph. "
                "Correct a wrong category yourself and it sticks."
            ),
            "action": "Images",
        },
        {
            "key": "price_sourcing", "label": "Price sources",
            "status": "manual",
            "detail": (
                "Prices come from you. Record where a price came from (shop, "
                "seller, quote) and tick verified when you checked it; "
                "unverified figures are labelled as estimates everywhere. "
                "Nothing scrapes a shop or fetches a live price."
            ),
            "action": "Inventory > Add or edit an item",
        },
        {
            "key": "mpesa", "label": "M-PESA", "status": "unavailable",
            "detail": (
                "There is no M-PESA connection. LifeSmart never reads your "
                "phone, your wallet balance or your statements; you type what "
                "you spent or received. On the Money page you can note the "
                "phone number an account is held on, and record its M-PESA and "
                "M-Shwari balances yourself - the number identifies the "
                "account, it links to nothing."
            ),
            "action": "Money > Add account",
        },
        {
            "key": "bank", "label": "Bank feeds", "status": "unavailable",
            "detail": (
                "No bank or card API is connected and none is planned here. "
                "A bank name and account number on the Money page are your own "
                "record of where money is kept. An account balance is only ever "
                "what you recorded, and an uninitialized balance stays unknown."
            ),
            "action": "Money > Add account",
        },
        {
            "key": "delivery_channels", "label": "Email, SMS and push alerts",
            "status": "not_configured",
            "detail": (
                "Reminders appear inside the app only. No mail or SMS provider "
                "is configured, so nothing is delivered to your phone or "
                "inbox - the preference toggles gate in-app reminders."
            ),
            "action": "Notifications",
        },
        {
            "key": "backup", "label": "Backups", "status": "manual",
            "detail": (
                "Your data is a single SQLite file plus the images folder. "
                "Copy them, or download the export on this page and restore it "
                "later, to keep a backup. Nothing happens automatically, and no "
                "backup leaves this machine unless you take it off yourself."
            ),
            "action": "Settings > Your data",
        },
    ]


@router.get("", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db),
                  user: User = Depends(get_current_user),
                  settings: Settings = Depends(get_settings)):
    counts = account_service.storage_counts(db, user)
    # Only the single-user desktop app gets a path: it is the person's own
    # machine, and they need the location to back the file up. Hosted mode
    # returns None rather than leaking a server path through an API.
    data_dir = str(data_home()) if settings.local_single_user else None
    return {
        "profile": UserOut.model_validate(user),
        "preferences": notifications.get_or_create(db, user.id),
        "integrations": integrations(settings),
        "privacy": {
            "local_only": settings.local_single_user,
            "data_dir": data_dir,
            "stored": counts,
            "row_total": account_service.total_rows(counts),
            "excluded": account_service.NOT_EXPORTED,
            "statement": PRIVACY_STATEMENT,
        },
        "export_note": EXPORT_NOTE,
    }
