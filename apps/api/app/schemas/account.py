"""Account operations contracts: the factory reset and the restore.

The confirmation phrase is required in the body, not assumed from the HTTP
verb, because the desktop app signs you in automatically - there is no
password to re-enter, so the typed word is the only deliberate step. Both
destructive operations use it: a reset deletes, and a restore overwrites.

An archive is carried as base64 inside JSON rather than as a multipart upload,
so this route needs no new dependency and reports errors the same way every
other route in the app does.
"""
from pydantic import BaseModel

CONFIRM_PHRASE = "RESET"
RESTORE_CONFIRM_PHRASE = "RESTORE"


class ResetRequest(BaseModel):
    confirm: str

    def confirmed(self) -> bool:
        return self.confirm.strip().upper() == CONFIRM_PHRASE


class ResetResult(BaseModel):
    deleted: dict[str, int]
    deleted_total: int
    kept: list[str]
    reseeded: list[str]
    note: str


class RestoreInspectRequest(BaseModel):
    """Just the archive. Reading it cannot change anything, so it asks for no
    confirmation phrase - and it writes nothing."""

    archive_base64: str


class RestoreRequest(RestoreInspectRequest):
    confirm: str

    def confirmed(self) -> bool:
        return self.confirm.strip().upper() == RESTORE_CONFIRM_PHRASE


class RestorePreviewTable(BaseModel):
    key: str
    label: str
    archive_rows: int
    current_rows: int


class RestorePreview(BaseModel):
    """What a restore would do, stated before it is possible to undo it.

    Both figures are shown per table rather than one total, because "12 rows
    will be replaced" hides the fact that the archive carries no goals at all.
    """

    generated_at: str | None
    currency_of_origin: str | None
    current_currency: str
    photo_links_kept: int
    photo_links_cleared: int
    archive_total: int
    current_total: int
    warnings: list[str]
    tables: list[RestorePreviewTable]


class RestoreResult(BaseModel):
    """Exactly what came back, per table, and what it replaced."""

    written: dict[str, int]
    written_total: int
    replaced: dict[str, int]
    replaced_total: int
    generated_at: str | None
    currency: str
    currency_changed_from: str | None
    photo_links_kept: int
    photo_links_cleared: int
    warnings: list[str]
    reseeded_categories: bool
    kept: list[str]
    note: str
