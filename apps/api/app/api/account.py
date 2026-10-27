"""Account data routes: take everything with you, or empty the account.

Both are authenticated and both stay inside one account's rows. The reset is
the destructive one, so it requires the confirmation phrase in the body and
reports exactly what it removed rather than a vague success message.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.account import CONFIRM_PHRASE, ResetRequest, ResetResult
from app.services import account as account_service
from app.services import export as export_service

router = APIRouter(prefix="/api/account", tags=["account"])

RESET_NOTE = (
    "Every record owned by this account was deleted. The account itself, your "
    "profile details and your image files were left alone, and categories were "
    "reset to the starter list. The app cannot undo this - if you downloaded an "
    "export first, that file is your only copy of what was here."
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
