"""Student Life API: fee obligations, payments, accommodation and food budget.

Fee payment is transactional and idempotent per (user, key): it records a
confirmed payment, writes the matching expense transaction and reduces the
outstanding balance in one commit. Nothing is ever claimed paid/booked without
the user recording it (spec 4.10).
"""
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned
from app.core.database import get_db
from app.models.finance import Account, Transaction
from app.models.goal import Goal
from app.models.student import (
    FeeObligation,
    FeePayment,
    FoodBudget,
    HostelOption,
)
from app.models.user import User
from app.schemas.student import (
    FeeCreate,
    FeeOut,
    FeePaymentCreate,
    FeePaymentOut,
    FeeUpdate,
    FoodBudgetOut,
    FoodBudgetUpdate,
    HostelAvailabilityUpdate,
    HostelCreate,
    HostelOut,
    HostelUpdate,
    StudentSummary,
)

router = APIRouter(prefix="/api/student", tags=["student"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Fees ---

def _fee_out(fee: FeeObligation) -> FeeOut:
    out = FeeOut.model_validate(fee)
    out.outstanding_minor = max(fee.amount_due_minor - fee.amount_paid_minor, 0)
    if out.outstanding_minor == 0:
        out.status = "paid"
    elif fee.amount_paid_minor > 0:
        out.status = "partial"
    else:
        out.status = "unpaid"
    return out


def _get_fee(db: Session, fee_id: int, user_id: int) -> FeeObligation:
    fee = get_owned(db, FeeObligation, fee_id, user_id)
    if fee.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    return fee


def _validate_goal(db: Session, user: User, goal_id: int | None) -> None:
    if goal_id is not None:
        get_owned(db, Goal, goal_id, user.id)


@router.get("/fees", response_model=list[FeeOut])
def list_fees(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    fees = db.scalars(
        select(FeeObligation)
        .where(FeeObligation.user_id == user.id, FeeObligation.deleted_at.is_(None))
        .order_by(FeeObligation.due_on.asc().nullslast(), FeeObligation.created_at.desc())
    ).all()
    return [_fee_out(f) for f in fees]


@router.post("/fees", response_model=FeeOut, status_code=201)
def create_fee(body: FeeCreate, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    _validate_goal(db, user, body.goal_id)
    fee = FeeObligation(user_id=user.id, **body.model_dump())
    db.add(fee)
    db.commit()
    return _fee_out(fee)


@router.put("/fees/{fee_id}", response_model=FeeOut)
def update_fee(fee_id: int, body: FeeUpdate, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    fee = _get_fee(db, fee_id, user.id)
    data = body.model_dump(exclude_unset=True)
    _validate_goal(db, user, data.get("goal_id"))
    for field, value in data.items():
        setattr(fee, field, value)
    db.commit()
    return _fee_out(fee)


@router.delete("/fees/{fee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fee(fee_id: int, confirm: bool = Query(default=False),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not confirm:
        raise HTTPException(status_code=400, detail="Deletion requires confirm=true")
    fee = _get_fee(db, fee_id, user.id)
    fee.deleted_at = _now()
    db.commit()
    return None


@router.get("/fees/{fee_id}/payments", response_model=list[FeePaymentOut])
def list_payments(fee_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    fee = _get_fee(db, fee_id, user.id)
    return db.scalars(
        select(FeePayment)
        .where(FeePayment.fee_id == fee.id)
        .order_by(FeePayment.occurred_on.desc(), FeePayment.id.desc())
    ).all()


@router.post("/fees/{fee_id}/payments", response_model=FeePaymentOut, status_code=201)
def record_payment(fee_id: int, body: FeePaymentCreate, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    existing = db.scalars(
        select(FeePayment).where(
            FeePayment.user_id == user.id,
            FeePayment.idempotency_key == body.idempotency_key,
        )
    ).first()
    if existing:
        db.rollback()
        return existing

    fee = _get_fee(db, fee_id, user.id)
    account = None
    if body.account_id is not None:
        account = get_owned(db, Account, body.account_id, user.id)

    txn = Transaction(
        user_id=user.id,
        type="expense",
        amount_minor=body.amount_minor,
        currency=user.currency,
        occurred_on=body.occurred_on or date.today(),
        category="fees",
        description=f"Fee payment: {fee.name}",
        from_account_id=account.id if account else None,
        reference=body.reference,
        idempotency_key=f"fee:{body.idempotency_key}",
    )
    db.add(txn)
    db.flush()

    payment = FeePayment(
        fee_id=fee.id,
        user_id=user.id,
        amount_minor=body.amount_minor,
        currency=user.currency,
        occurred_on=txn.occurred_on,
        transaction_id=txn.id,
        reference=body.reference,
        idempotency_key=body.idempotency_key,
    )
    db.add(payment)
    fee.amount_paid_minor += body.amount_minor
    if fee.reference is None and body.reference:
        fee.reference = body.reference
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalars(
            select(FeePayment).where(
                FeePayment.user_id == user.id,
                FeePayment.idempotency_key == body.idempotency_key,
            )
        ).first()
        if existing:
            return existing
        raise
    return payment


# --- Accommodation ---

def _get_hostel(db: Session, hostel_id: int, user_id: int) -> HostelOption:
    hostel = get_owned(db, HostelOption, hostel_id, user_id)
    if hostel.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    return hostel


@router.get("/hostels", response_model=list[HostelOut])
def list_hostels(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(
        select(HostelOption)
        .where(HostelOption.user_id == user.id, HostelOption.deleted_at.is_(None))
        .order_by(HostelOption.created_at.desc())
    ).all()


@router.post("/hostels", response_model=HostelOut, status_code=201)
def create_hostel(body: HostelCreate, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    hostel = HostelOption(user_id=user.id, **body.model_dump())
    db.add(hostel)
    db.commit()
    return hostel


@router.put("/hostels/{hostel_id}", response_model=HostelOut)
def update_hostel(hostel_id: int, body: HostelUpdate, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    hostel = _get_hostel(db, hostel_id, user.id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(hostel, field, value)
    db.commit()
    return hostel


@router.post("/hostels/{hostel_id}/availability", response_model=HostelOut)
def update_availability(hostel_id: int, body: HostelAvailabilityUpdate,
                        db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """Recording what the user saw updates the last-checked time; the app only
    reflects the user's report, it never independently asserts availability."""
    hostel = _get_hostel(db, hostel_id, user.id)
    hostel.status = body.status
    hostel.last_checked_at = _now()
    db.commit()
    return hostel


@router.delete("/hostels/{hostel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_hostel(hostel_id: int, confirm: bool = Query(default=False),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    if not confirm:
        raise HTTPException(status_code=400, detail="Deletion requires confirm=true")
    hostel = _get_hostel(db, hostel_id, user.id)
    hostel.deleted_at = _now()
    db.commit()
    return None


# --- Food budget ---

def _food_out(fb: FoodBudget) -> FoodBudgetOut:
    out = FoodBudgetOut.model_validate(fb)
    if fb.weekly_budget_minor is not None:
        out.daily_estimate_minor = int(
            (Decimal(fb.weekly_budget_minor) / Decimal("7")).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
    return out


@router.get("/food-budget", response_model=FoodBudgetOut)
def get_food_budget(db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    fb = db.scalars(
        select(FoodBudget).where(FoodBudget.user_id == user.id)
    ).first()
    if fb is None:
        fb = FoodBudget(user_id=user.id, weekly_budget_minor=None)
        db.add(fb)
        db.commit()
    return _food_out(fb)


@router.put("/food-budget", response_model=FoodBudgetOut)
def update_food_budget(body: FoodBudgetUpdate, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    fb = db.scalars(
        select(FoodBudget).where(FoodBudget.user_id == user.id)
    ).first()
    if fb is None:
        fb = FoodBudget(user_id=user.id)
        db.add(fb)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(fb, field, value)
    fb.updated_at = _now()
    db.commit()
    return _food_out(fb)


# --- Summary ---

@router.get("/summary", response_model=StudentSummary)
def student_summary(db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    fees = db.scalars(
        select(FeeObligation).where(
            FeeObligation.user_id == user.id, FeeObligation.deleted_at.is_(None)
        )
    ).all()
    today = date.today()
    due = paid = outstanding = 0
    overdue_count = 0
    for f in fees:
        due += f.amount_due_minor
        paid += f.amount_paid_minor
        rem = max(f.amount_due_minor - f.amount_paid_minor, 0)
        outstanding += rem
        if rem > 0 and f.due_on is not None and f.due_on < today:
            overdue_count += 1
    hostel_count = db.scalar(
        select(func.count()).select_from(HostelOption).where(
            HostelOption.user_id == user.id, HostelOption.deleted_at.is_(None)
        )
    ) or 0
    return StudentSummary(
        total_fees_due_minor=due,
        total_fees_paid_minor=paid,
        total_fees_outstanding_minor=outstanding,
        overdue_fees_count=overdue_count,
        hostel_options_count=hostel_count,
    )
