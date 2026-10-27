"""Settings contracts: who you are, what is stored, what is connected.

The integration list exists so the product can state, per capability, whether
it actually works, is manual, is not configured or does not exist - rather
than implying a connection it does not have.
"""
from typing import Literal

from pydantic import BaseModel

from app.schemas.auth import UserOut
from app.schemas.notifications import NotificationPreferenceOut

# available = works now; on_demand = present but only runs when you start it;
# manual = you do the work, the app only records it; not_configured = built but
# switched off; unavailable = no such connection exists in this product.
IntegrationStatus = Literal[
    "available", "on_demand", "manual", "not_configured", "unavailable"
]


class IntegrationOut(BaseModel):
    key: str
    label: str
    status: IntegrationStatus
    detail: str
    # Where in the app the user acts on it, when there is somewhere to go.
    action: str | None = None


class StoredTableOut(BaseModel):
    key: str
    label: str
    rows: int


class ExcludedTableOut(BaseModel):
    key: str
    label: str
    reason: str


class PrivacyOut(BaseModel):
    # True when this deployment is the single-user desktop app.
    local_only: bool
    # The app's own data directory, and only then: on a hosted deployment this
    # is None because a server path is not the user's business (and never an
    # arbitrary file path through an API).
    data_dir: str | None
    stored: list[StoredTableOut]
    row_total: int
    excluded: list[ExcludedTableOut]
    statement: list[str]


class SettingsOut(BaseModel):
    profile: UserOut
    preferences: NotificationPreferenceOut
    integrations: list[IntegrationOut]
    privacy: PrivacyOut
    export_note: str
