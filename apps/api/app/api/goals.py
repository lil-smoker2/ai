"""Goals API: costed targets with deterministic, explainable calculations.

Money goals track saved contributions; quantity goals track progress toward a
target quantity. required_monthly_saving is only computed when there is a
future deadline - never divided by zero.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned
from app.core.database import get_db
from app.models.finance import Account, Transaction
from app.models.goal import Goal, GoalContribution
from app.models.inventory import InventoryItem
from app.models.user import User
from app.schemas.goals import ContributionCreate, ContributionOut, GoalCreate, GoalOut
from app.services import forecasting as forecasting_service

router = APIRouter(prefix="/api/goals", tags=["goals"])


def _months_remaining(deadline: date, today: date) -> int | None:
    """Whole or partial months from today until the deadline, via exact days."""
    if deadline <= today:
        return None
    days = (deadline - today).days
    return max(int(Decimal(days) / Decimal("30.44")), 1)


def _goal_out(db: Session, goal: Goal) -> GoalOut:
    saved = db.scalar(
        select(func.coalesce(func.sum(GoalContribution.amount_minor), 0)).where(
            GoalContribution.goal_id == goal.id,
            GoalContribution.user_id == goal.user_id,
        )
    ) or 0
    out = GoalOut.model_validate(goal)
    out.amount_saved_minor = saved

    if goal.type == "money" and goal.target_amount_minor is not None:
        out.remaining_amount_minor = max(goal.target_amount_minor - saved, 0)

    if goal.type == "quantity" and goal.target_quantity is not None:
        current = goal.current_quantity or 0
        out.remaining_quantity = max(goal.target_quantity - current, 0)
        if goal.estimated_unit_cost_minor is not None:
            out.estimated_remaining_cost_minor = (
                out.remaining_quantity * goal.estimated_unit_cost_minor
            )

    today = date.today()
    if goal.deadline is None:
        out.deadline_state = "no_deadline"
    elif goal.deadline < today:
        out.deadline_state = "deadline_passed"
    else:
        out.deadline_state = "ok"
        months = _months_remaining(goal.deadline, today)
        target = out.remaining_amount_minor
        if target is None and goal.type == "quantity" and goal.estimated_unit_cost_minor is not None:
            target = out.estimated_remaining_cost_minor
        if target and months:
            # Round up so plans never under-fund the goal.
            out.required_monthly_saving_minor = -(-target // months)

    # A completion date exists only where contributions show real recent
    # saving; otherwise this stays None instead of an invented date.
    target_left = out.remaining_amount_minor
    if target_left is None and goal.type == "quantity" and goal.estimated_unit_cost_minor is not None:
        target_left = out.estimated_remaining_cost_minor
    out.projection = forecasting_service.project_goal_completion(
        db, goal, target_left, today=today
    )
    return out


@router.get("", response_model=list[GoalOut])
def list_goals(status_filter: str | None = Query(default=None, alias="status",
                 pattern="^(active|paused|completed)$"),
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    query = select(Goal).where(Goal.user_id == user.id)
    if status_filter:
        query = query.where(Goal.status == status_filter)
    goals = db.scalars(query.order_by(Goal.created_at.desc())).all()
    return [_goal_out(db, g) for g in goals]


@router.post("", response_model=GoalOut, status_code=201)
def create_goal(body: GoalCreate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    if body.inventory_item_id is not None:
        get_owned(db, InventoryItem, body.inventory_item_id, user.id)
    goal = Goal(user_id=user.id, **body.model_dump())
    db.add(goal)
    db.commit()
    return _goal_out(db, goal)


@router.get("/{goal_id}", response_model=GoalOut)
def get_goal(goal_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    return _goal_out(db, get_owned(db, Goal, goal_id, user.id))


@router.get("/{goal_id}/contributions", response_model=list[ContributionOut])
def list_contributions(goal_id: int, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    goal = get_owned(db, Goal, goal_id, user.id)
    return db.scalars(
        select(GoalContribution)
        .where(GoalContribution.goal_id == goal.id)
        .order_by(GoalContribution.occurred_on.desc())
    ).all()


@router.post("/{goal_id}/contributions", response_model=ContributionOut, status_code=201)
def add_contribution(goal_id: int, body: ContributionCreate,
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    goal = get_owned(db, Goal, goal_id, user.id)
    if goal.status == "completed":
        raise HTTPException(status_code=409, detail="Goal is already completed")
    if body.account_id is not None:
        get_owned(db, Account, body.account_id, user.id)
    if body.transaction_id is not None:
        get_owned(db, Transaction, body.transaction_id, user.id)
    contribution = GoalContribution(
        goal_id=goal.id,
        user_id=user.id,
        amount_minor=body.amount_minor,
        occurred_on=body.occurred_on or date.today(),
        account_id=body.account_id,
        transaction_id=body.transaction_id,
        note=body.note,
    )
    db.add(contribution)
    db.commit()
    return contribution


@router.post("/{goal_id}/complete", response_model=GoalOut)
def complete_goal(goal_id: int, force: bool = Query(default=False),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Completion requires validated criteria unless the user explicitly
    confirms a force-complete (audit-visible in the response status)."""
    goal = get_owned(db, Goal, goal_id, user.id)
    out = _goal_out(db, goal)
    criteria_met = (
        (goal.type == "money" and out.remaining_amount_minor == 0)
        or (goal.type == "quantity" and (out.remaining_quantity or 0) == 0)
    )
    if not criteria_met and not force:
        raise HTTPException(
            status_code=422,
            detail="Completion criteria not met; pass force=true to confirm manually",
        )
    goal.status = "completed"
    goal.completed_at = datetime.now(timezone.utc)
    db.commit()
    return _goal_out(db, goal)


@router.post("/{goal_id}/pause", response_model=GoalOut)
def pause_goal(goal_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    goal = get_owned(db, Goal, goal_id, user.id)
    if goal.status == "completed":
        raise HTTPException(status_code=409, detail="Completed goals cannot be paused")
    goal.status = "paused"
    db.commit()
    return _goal_out(db, goal)
