"""Notifications API: the preference switches, and what needs attention today.

Local-first, so these gate the app's own reminders only - nothing here sends
email or push. Reading the preferences creates a default row the first time so
the client always has something to render.

/alerts is computed on every call and stores nothing. See app.services.alerts
for why an alert that was written down would be a worse answer than one
recomputed from the records it describes.
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
    AlertsOut,
    NotificationPreferenceOut,
    NotificationPreferenceUpdate,
)
from app.services import alerts as alerts_service

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


@router.get("/alerts", response_model=AlertsOut)
def get_alerts(db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """Every alert the saved records support right now, honouring the switches.

    The response is not cached, deliberately: a client that holds a stale list
    would keep telling the user about a fee they have just paid off.
    """
    pref = get_or_create(db, user.id)
    return alerts_service.build_alerts(db, user, pref)


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
