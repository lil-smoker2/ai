"""Net worth API: the value of what you own, read and saved as a record.

The single endpoint prices every inventory item (what you have, what you still
need, what one costs, what that comes to) and reports the saved snapshot. There
is deliberately no write route for the total - it is derived, so it can never
be typed in wrong or left stale.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.valuation import Valuation
from app.services import valuation as valuation_service

router = APIRouter(prefix="/api/networth", tags=["networth"])


@router.get("", response_model=Valuation)
def get_valuation(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return valuation_service.valuation(db, user)
