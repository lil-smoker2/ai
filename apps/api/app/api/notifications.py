"""Notification preferences API: read and update a user's in-app alert toggles.

Local-first, so these gate the app's own reminders only. Reading creates a
default row the first time so the client always has something to render.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.notifications import NotificationPreference
from app.models.user import User
from app.schemas.notifications import (
    NotificationPreferenceOut,
    NotificationPreferenceUpdate,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def get_or_create(db: Session, user_id: int) -> NotificationPreference:
    """Also read by the Settings page, so the app never shows two answers."""
    pref = db.scalars(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    ).first()
    if pref is None:
        pref = NotificationPreference(user_id=user_id)
        db.add(pref)
        db.commit()
        db.refresh(pref)
    return pref


@router.get("/preferences", response_model=NotificationPreferenceOut)
def get_preferences(db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return get_or_create(db, user.id)


@router.put("/preferences", response_model=NotificationPreferenceOut)
def update_preferences(body: NotificationPreferenceUpdate,
                       db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    pref = get_or_create(db, user.id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(pref, field, value)
    pref.updated_at = datetime.now(timezone.utc)
    db.commit()
    return pref
