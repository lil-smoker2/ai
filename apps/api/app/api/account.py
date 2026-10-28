"""Account data routes: take everything with you, put it back, or empty the
account.

All three are authenticated and all three stay inside one account's rows. The
reset and the restore are the destructive ones, so both require the
confirmation phrase in the body and report exactly what they did rather than a
vague success message. A restore is refused before it writes anything if any
part of the archive cannot be accounted for.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.account import (
    CONFIRM_PHRASE,
    RESTORE_CONFIRM_PHRASE,
    ResetRequest,
    ResetResult,
    RestoreInspectRequest,
    RestorePreview,
    RestoreRequest,
    RestoreResult,
)
from app.services import account as account_service
from app.services import export as export_service
from app.services import restore as restore_service
from app.services.restore import RestoreError

router = APIRouter(prefix="/api/account", tags=["account"])

RESET_NOTE = (
    "Every record owned by this account was deleted. The account itself, your "
    "profile details and your image files were left alone, and categories were "
    "reset to the starter list. The app cannot undo this on its own - but an "
    "export you downloaded earlier can be restored under Settings > Your data."
)


@router.get("/export")
def download_export(db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Every row this account owns, as a zip (JSON + one CSV per table)."""
    archive, filename = export_service.export_archive(db, user)
    return Response(
        content=archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Personal data must not sit in a shared cache.
            "Cache-Control": "no-store",
        },
    )


@router.post("/reset", response_model=ResetResult)
def reset_account(body: ResetRequest, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Delete every record this account owns, keeping the sign-in."""
    if not body.confirmed():
        raise HTTPException(
            status_code=400,
            detail=f"Type {CONFIRM_PHRASE} to confirm. Nothing was deleted.",
        )
    result = account_service.reset(db, user)
    result["note"] = RESET_NOTE
    return result


@router.post("/restore/preview", response_model=RestorePreview)
def preview_restore(body: RestoreInspectRequest, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Read an archive and say what restoring it would do.

    Nothing is written here, and nothing is remembered between the two calls:
    the restore re-reads and re-checks the archive it is given, because a
    preview that earned trust would be a promise about a different moment.
    """
    try:
        payload = restore_service.decode_archive(body.archive_base64)
        return restore_service.preview(payload, db, user)
    except RestoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/restore", response_model=RestoreResult)
def restore_account(body: RestoreRequest, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Replace this account's records with the ones in an archive it exported."""
    if not body.confirmed():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Type {RESTORE_CONFIRM_PHRASE} to confirm. A restore replaces "
                "every record in this account. Nothing was changed."
            ),
        )
    try:
        payload = restore_service.decode_archive(body.archive_base64)
        return restore_service.restore(payload, db, user)
    except RestoreError as exc:
        # The service rolled back anything it had begun, so the account is as
        # it was. The reason is the useful part of the message.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
