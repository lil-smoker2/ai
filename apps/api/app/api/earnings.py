"""Savings & Earnings API: income sources, business records, forecast.

net_business_profit = revenue - expenses (spec 4.6). The forecast's
available_for_planning is a planning estimate - recorded balance plus expected
recurring income minus outstanding goal obligations - and is only produced
when a recorded balance exists. Expected income is never counted as received.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned
from app.core.database import get_db
from app.models.earnings import BusinessRecord, IncomeSource
from app.models.finance import Account, Transaction
from app.models.goal import Goal, GoalContribution
from app.models.user import User
from app.schemas.earnings import (
    BusinessProfit,
    BusinessRecordCreate,
    BusinessRecordOut,
    EarningsSummary,
    IncomeSourceCreate,
    IncomeSourceOut,
    IncomeSourceUpdate,
)

router = APIRouter(prefix="/api/earnings", tags=["earnings"])

# Expected-amount -> per-month factors (calendar-accurate enough for planning).
_MONTHLY_FACTORS: dict[str, Decimal] = {
    "daily": Decimal("30.44"),
    "weekly": Decimal("30.44") / Decimal("7"),
    "monthly": Decimal("1"),
    "yearly": Decimal("1") / Decimal("12"),
    "once": Decimal("0"),  # not recurring: excluded from the monthly run-rate
}


def _monthly_expected(source: IncomeSource) -> int:
    factor = _MONTHLY_FACTORS.get(source.frequency, Decimal("0"))
    value = Decimal(source.expected_amount_minor) * factor
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _source_out(source: IncomeSource) -> IncomeSourceOut:
    out = IncomeSourceOut.model_validate(source)
    out.monthly_expected_minor = _monthly_expected(source)
    return out


def _account_balance(db: Session, account: Account) -> int | None:
    # Reuse the exact same balance logic as the Money API.
    from app.api.finance import _account_balance as _bal

    return _bal(db, account)


# --- Income sources ---

@router.get("/income-sources", response_model=list[IncomeSourceOut])
def list_income_sources(db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    rows = db.scalars(
        select(IncomeSource)
        .where(IncomeSource.user_id == user.id)
        .order_by(IncomeSource.created_at.desc())
    ).all()
    return [_source_out(s) for s in rows]


@router.post("/income-sources", response_model=IncomeSourceOut, status_code=201)
def create_income_source(body: IncomeSourceCreate, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    source = IncomeSource(user_id=user.id, **body.model_dump())
    db.add(source)
    db.commit()
    return _source_out(source)


@router.put("/income-sources/{source_id}", response_model=IncomeSourceOut)
def update_income_source(source_id: int, body: IncomeSourceUpdate,
                         db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    source = get_owned(db, IncomeSource, source_id, user.id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    db.commit()
    return _source_out(source)


@router.delete("/income-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_income_source(source_id: int, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    source = get_owned(db, IncomeSource, source_id, user.id)
    db.delete(source)
    db.commit()
    return None


# --- Business records ---

@router.get("/business", response_model=list[BusinessRecordOut])
def list_business_records(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(BusinessRecord).where(BusinessRecord.user_id == user.id)
    if date_from:
        query = query.where(BusinessRecord.occurred_on >= date_from)
    if date_to:
        query = query.where(BusinessRecord.occurred_on <= date_to)
    return db.scalars(query.order_by(BusinessRecord.occurred_on.desc(),
                                     BusinessRecord.id.desc())).all()


@router.post("/business", response_model=BusinessRecordOut, status_code=201)
def create_business_record(body: BusinessRecordCreate, db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)):
    if body.transaction_id is not None:
        get_owned(db, Transaction, body.transaction_id, user.id)
    record = BusinessRecord(
        user_id=user.id,
        business_name=body.business_name,
        type=body.type,
        amount_minor=body.amount_minor,
        category=body.category,
        occurred_on=body.occurred_on or date.today(),
        transaction_id=body.transaction_id,
        notes=body.notes,
    )
    db.add(record)
    db.commit()
    return record


@router.get("/business/profit", response_model=list[BusinessProfit])
def business_profit(date_from: date | None = Query(default=None),
                    date_to: date | None = Query(default=None),
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Per-business net profit = revenue - expenses over the window."""
    base = select(BusinessRecord).where(BusinessRecord.user_id == user.id)
    if date_from:
        base = base.where(BusinessRecord.occurred_on >= date_from)
    if date_to:
        base = base.where(BusinessRecord.occurred_on <= date_to)
    rows = db.scalars(base).all()

    by_business: dict[str, dict[str, int]] = {}
    for r in rows:
        agg = by_business.setdefault(r.business_name, {"revenue": 0, "expense": 0})
        agg[r.type] += r.amount_minor
    return [
        BusinessProfit(
            business_name=name,
            revenue_minor=agg["revenue"],
            expenses_minor=agg["expense"],
            net_profit_minor=agg["revenue"] - agg["expense"],
        )
        for name, agg in sorted(by_business.items())
    ]


@router.delete("/business/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business_record(record_id: int, db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)):
    record = get_owned(db, BusinessRecord, record_id, user.id)
    db.delete(record)
    db.commit()
    return None


# --- Forecast ---

@router.get("/summary", response_model=EarningsSummary)
def earnings_summary(db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    accounts = db.scalars(select(Account).where(Account.user_id == user.id)).all()
    initialized = [a for a in accounts if a.initialized]
    recorded_balance = (
        sum(_account_balance(db, a) for a in initialized) if initialized else None
    )

    sources = db.scalars(
        select(IncomeSource).where(
            IncomeSource.user_id == user.id, IncomeSource.active.is_(True)
        )
    ).all()
    monthly_expected = sum(_monthly_expected(s) for s in sources)

    today = date.today()
    month_start = today.replace(day=1)

    def business_total(kind: str) -> int:
        return db.scalar(
            select(func.coalesce(func.sum(BusinessRecord.amount_minor), 0)).where(
                BusinessRecord.user_id == user.id,
                BusinessRecord.type == kind,
                BusinessRecord.occurred_on >= month_start,
                BusinessRecord.occurred_on <= today,
            )
        ) or 0

    revenue = business_total("revenue")
    expenses = business_total("expense")

    savings_this_month = db.scalar(
        select(func.coalesce(func.sum(GoalContribution.amount_minor), 0)).where(
            GoalContribution.user_id == user.id,
            GoalContribution.occurred_on >= month_start,
            GoalContribution.occurred_on <= today,
        )
    ) or 0
    total_saved = db.scalar(
        select(func.coalesce(func.sum(GoalContribution.amount_minor), 0)).where(
            GoalContribution.user_id == user.id
        )
    ) or 0

    outstanding = 0
    for goal in db.scalars(
        select(Goal).where(Goal.user_id == user.id, Goal.status == "active")
    ).all():
        if goal.type == "money" and goal.target_amount_minor is not None:
            saved = db.scalar(
                select(func.coalesce(func.sum(GoalContribution.amount_minor), 0)).where(
                    GoalContribution.goal_id == goal.id
                )
            ) or 0
            outstanding += max(goal.target_amount_minor - saved, 0)

    # Planning estimate only when a recorded balance exists (never fake zero).
    available = None
    if recorded_balance is not None:
        available = recorded_balance + monthly_expected - outstanding

    assumptions = [
        "available_for_planning is a planning estimate, not a bank balance.",
        "Monthly expected income is normalized from active income sources "
        "(daily x30.44, weekly x4.35, yearly /12); one-time sources are excluded "
        "from the run-rate and never counted as already received.",
        "Outstanding obligations are the remaining amounts of active money goals; "
        "planned essential expenses (rent, food, fees) are not yet captured.",
    ]
    if recorded_balance is None:
        assumptions.append(
            "No initialized account balance, so available_for_planning is unknown."
        )

    return EarningsSummary(
        recorded_available_balance_minor=recorded_balance,
        monthly_expected_income_minor=monthly_expected,
        business_revenue_this_month_minor=revenue,
        business_expenses_this_month_minor=expenses,
        business_net_profit_this_month_minor=revenue - expenses,
        savings_contributed_this_month_minor=savings_this_month,
        total_saved_in_goals_minor=total_saved,
        outstanding_obligations_minor=outstanding,
        available_for_planning_minor=available,
        assumptions=assumptions,
    )
