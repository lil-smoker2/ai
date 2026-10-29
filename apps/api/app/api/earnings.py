"""Savings & Earnings API: income sources, business records, savings vehicles
and the forecast.

net_business_profit = revenue - expenses (spec 4.6). The forecast's
available_for_planning is a planning estimate - recorded balance plus expected
recurring income minus outstanding goal obligations - and is only produced
when a recorded balance exists. Expected income is never counted as received.

Savings vehicles are the places money can sit, described by what the person was
told: a rate they recorded on a date, a holding they valued themselves. A
projection is arithmetic on those stated figures, records nothing, and lists the
assumptions it rests on. A betting site is kept apart from all of that - it gets
a link and a record of what it cost, never a projected return.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned
from app.core.database import get_db
from app.models.earnings import (
    BusinessRecord,
    IncomeSource,
    SavingsVehicle,
    VehicleFlow,
)
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
    Projection,
    ProjectionCreate,
    RISK_KINDS,
    VehicleCreate,
    VehicleFlowCreate,
    VehicleFlowOut,
    VehicleOut,
    VehicleUpdate,
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


# --- Savings vehicles: the places money can sit -------------------------------


def _flow_totals(db: Session, vehicle: SavingsVehicle) -> tuple[int, int, bool]:
    """Money put in, money that came back, and whether any of it was recorded.

    The third value matters: a vehicle with no records has not been told
    anything, which is not the same as a vehicle holding nothing.
    """
    rows = db.scalars(
        select(VehicleFlow).where(VehicleFlow.vehicle_id == vehicle.id)
    ).all()
    put_in = sum(r.amount_minor for r in rows if r.direction == "in")
    taken_out = sum(r.amount_minor for r in rows if r.direction == "out")
    return put_in, taken_out, bool(rows)


def _vehicle_out(db: Session, vehicle: SavingsVehicle) -> VehicleOut:
    out = VehicleOut.model_validate(vehicle)
    put_in, taken_out, recorded = _flow_totals(db, vehicle)
    if recorded:
        out.put_in_minor = put_in
        out.taken_out_minor = taken_out
        out.net_in_minor = put_in - taken_out
        if vehicle.value_minor is not None:
            # What it is worth now, plus anything already taken out, against
            # what went in. The only gain that can be stated from these records.
            out.gain_minor = vehicle.value_minor + taken_out - put_in
    return out


def _get_vehicle(db: Session, vehicle_id: int, user_id: int) -> SavingsVehicle:
    return get_owned(db, SavingsVehicle, vehicle_id, user_id)


@router.get("/vehicles", response_model=list[VehicleOut])
def list_vehicles(db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    rows = db.scalars(
        select(SavingsVehicle)
        .where(SavingsVehicle.user_id == user.id)
        .order_by(SavingsVehicle.created_at)
    ).all()
    return [_vehicle_out(db, v) for v in rows]


@router.post("/vehicles", response_model=VehicleOut, status_code=201)
def create_vehicle(body: VehicleCreate, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """Note a place money can sit, in the person's own words.

    The schema has already kept only the figures this kind of vehicle can carry:
    a rate stands with the date it was checked, a holding's value with the day
    it was valued, and a betting site carries neither.
    """
    vehicle = SavingsVehicle(user_id=user.id, **body.model_dump())
    db.add(vehicle)
    db.commit()
    return _vehicle_out(db, vehicle)


@router.put("/vehicles/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(vehicle_id: int, body: VehicleUpdate,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """Rewrite the card. The whole form is sent, so an emptied rate is removed
    rather than quietly kept, and the rules are the ones applied at creation."""
    vehicle = _get_vehicle(db, vehicle_id, user.id)
    for field, value in body.model_dump().items():
        setattr(vehicle, field, value)
    db.commit()
    return _vehicle_out(db, vehicle)


@router.delete("/vehicles/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """Forget a place, unless something was recorded against it.

    A card with savings, stakes or purchases on it is kept until those records
    are removed one by one: deleting the card would delete the person's record
    of what they did, silently and without a list of what went.
    """
    vehicle = _get_vehicle(db, vehicle_id, user.id)
    _put_in, _taken_out, recorded = _flow_totals(db, vehicle)
    if recorded:
        raise HTTPException(
            status_code=409,
            detail=(
                "This place has records against it. Remove them first, so "
                "nothing you saved or staked disappears with the card."
            ),
        )
    db.delete(vehicle)
    db.commit()
    return None


@router.post("/vehicles/{vehicle_id}/flows", response_model=VehicleFlowOut,
             status_code=201)
def add_vehicle_flow(vehicle_id: int, body: VehicleFlowCreate,
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Note money going in or coming back, as the person describes it.

    No account balance moves here. The Money page is where a transfer is real;
    duplicating it in both places would count the same money twice.
    """
    vehicle = _get_vehicle(db, vehicle_id, user.id)
    flow = VehicleFlow(
        vehicle_id=vehicle.id, user_id=user.id, **body.model_dump()
    )
    db.add(flow)
    db.commit()
    return flow


@router.get("/vehicles/{vehicle_id}/flows", response_model=list[VehicleFlowOut])
def list_vehicle_flows(vehicle_id: int, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    vehicle = _get_vehicle(db, vehicle_id, user.id)
    return db.scalars(
        select(VehicleFlow)
        .where(VehicleFlow.vehicle_id == vehicle.id)
        .order_by(VehicleFlow.occurred_on.desc(), VehicleFlow.id.desc())
    ).all()


@router.delete("/vehicle-flows/{flow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle_flow(flow_id: int, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """Remove one note. get_owned scopes it to this account's rows."""
    flow = get_owned(db, VehicleFlow, flow_id, user.id)
    db.delete(flow)
    db.commit()
    return None


@router.post("/vehicles/{vehicle_id}/project", response_model=Projection)
def project_vehicle(vehicle_id: int, body: ProjectionCreate,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """What the stated figures would give, without recording anything.

    Refused rather than guessed when no rate was entered: the app cannot look a
    platform's rate up, so any number it produced would be invented.
    """
    vehicle = _get_vehicle(db, vehicle_id, user.id)
    if vehicle.kind in RISK_KINDS:
        raise HTTPException(
            status_code=422,
            detail=(
                "A bet has no rate to project from. What you stake can be lost, "
                "and nothing here can say what it returns - record the stakes "
                "and what came back instead."
            ),
        )
    if vehicle.rate_percent is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "No rate recorded for this place. Enter the percentage the "
                "platform quoted you and the date you checked it, and the "
                "projection will say what it assumes."
            ),
        )

    rate = Decimal(str(vehicle.rate_percent))
    # Simple interest on purpose: compounding belongs to the platform's own
    # terms, which this app does not know, so the figure understates rather
    # than invents. The assumptions say so.
    interest = (
        Decimal(body.amount_minor) * rate / Decimal("100")
        * Decimal(body.months) / Decimal("12")
    )
    interest_minor = int(interest.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    checked = (
        f" on {vehicle.rate_checked_on.isoformat()}"
        if vehicle.rate_checked_on
        else ""
    )
    assumptions = [
        f"Uses the {rate.normalize():f}% a year you recorded{checked}. LifeSmart is offline "
        f"and did not verify it, and platforms change rates without telling you.",
        "Interest is not treated as earning more interest, so a platform that "
        "compounds monthly may pay a little more than this figure.",
        f"Assumes the rate holds for all {body.months} months, with nothing "
        "added and nothing withdrawn during that time.",
        "Nothing was recorded and no money moved. When you actually save it, "
        "record the transfer on the Money page so your balance agrees.",
        "Tax, withdrawal fees, minimum periods and any bonus the platform "
        "offers are not included - they are its terms, not known facts.",
    ]
    if vehicle.value_minor is not None:
        assumptions.append(
            "This place also has a saved valuation, which is a separate figure "
            "and not part of this projection."
        )

    return Projection(
        amount_minor=body.amount_minor,
        months=body.months,
        rate_percent=vehicle.rate_percent,
        rate_checked_on=vehicle.rate_checked_on,
        interest_minor=interest_minor,
        total_minor=body.amount_minor + interest_minor,
        assumptions=assumptions,
    )
