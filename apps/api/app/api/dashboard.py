"""Dashboard summary computed from saved records only."""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.finance import Account, Transaction
from app.models.goal import Goal, GoalContribution
from app.models.inventory import InventoryItem
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.services import valuation as valuation_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.api.finance import _account_balance  # reuse single balance logic

    accounts = db.scalars(select(Account).where(Account.user_id == user.id)).all()
    initialized = [a for a in accounts if a.initialized]
    total_available = (
        sum(_account_balance(db, a) for a in initialized) if initialized else None
    )

    today = date.today()
    month_start = today.replace(day=1)

    def month_total(txn_type: str) -> int:
        return db.scalar(
            select(func.coalesce(func.sum(Transaction.amount_minor), 0)).where(
                Transaction.user_id == user.id,
                Transaction.type == txn_type,
                Transaction.occurred_on >= month_start,
                Transaction.occurred_on <= today,
            )
        ) or 0

    savings_this_month = db.scalar(
        select(func.coalesce(func.sum(GoalContribution.amount_minor), 0)).where(
            GoalContribution.user_id == user.id,
            GoalContribution.occurred_on >= month_start,
            GoalContribution.occurred_on <= today,
        )
    ) or 0

    active_goals = db.scalars(
        select(Goal).where(Goal.user_id == user.id, Goal.status == "active")
    ).all()
    outstanding = 0
    for goal in active_goals:
        if goal.type == "money" and goal.target_amount_minor is not None:
            saved = db.scalar(
                select(func.coalesce(func.sum(GoalContribution.amount_minor), 0)).where(
                    GoalContribution.goal_id == goal.id
                )
            ) or 0
            outstanding += max(goal.target_amount_minor - saved, 0)

    items = db.scalars(
        select(InventoryItem).where(
            InventoryItem.user_id == user.id, InventoryItem.deleted_at.is_(None)
        )
    ).all()
    below_target = [
        i for i in items
        if i.target_quantity is not None and i.quantity_owned < i.target_quantity
    ]
    price_needed = [i for i in below_target if i.estimated_unit_cost_minor is None]
    shortage_cost = (
        sum(
            (i.target_quantity - i.quantity_owned) * i.estimated_unit_cost_minor
            for i in below_target
            if i.estimated_unit_cost_minor is not None
        )
        if below_target
        else 0
    )

    return DashboardSummary(
        total_available_minor=total_available,
        income_this_month_minor=month_total("income"),
        expenses_this_month_minor=month_total("expense"),
        savings_this_month_minor=savings_this_month,
        active_goals=len(active_goals),
        outstanding_goal_amount_minor=outstanding,
        distinct_inventory_items=len(items),
        items_below_target=len(below_target),
        # Null (not zero) when any shortage lacks a price.
        estimated_shortage_cost_minor=(
            None if price_needed else shortage_cost if below_target else 0
        ),
        price_needed_items=len(price_needed),
        # The recorded worth of what is owned, not a freshly invented number.
        net_worth_minor=valuation_service.saved_net_worth(db, user),
    )
