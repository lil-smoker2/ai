"""Reports API: monthly cash flow, spending by category, balance history,
savings/goal progress, inventory shortage cost, business profit and upcoming
obligations - all computed from saved records only.

Honesty rules carried through every section: transfers are never counted as
income or expense; an uninitialized balance or an unpriced shortage is reported
as unknown (null), not zero; a fee is only "paid" to the extent payments were
recorded. Filters (date range, account, category) narrow the underlying records
before any figure is derived.
"""
from collections import defaultdict
from csv import writer as csv_writer
from datetime import date
from io import StringIO

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned
from app.core.database import get_db
from app.models.earnings import BusinessRecord
from app.models.finance import Account, Transaction
from app.models.goal import Goal, GoalContribution
from app.models.inventory import InventoryItem
from app.models.student import FeeObligation
from app.models.user import User
from app.schemas.reports import (
    BalanceHistory,
    BalancePoint,
    BusinessReport,
    CashFlow,
    CategorySpend,
    GoalProgress,
    ObligationItem,
    ObligationsReport,
    ReportPeriod,
    ReportSummary,
    SavingsProgress,
    ShortageReport,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])


# --- helpers ----------------------------------------------------------------

def _month_str(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _month_tuple(s: str) -> tuple[int, int]:
    y, m = s.split("-")
    return int(y), int(m)


def _next_month(t: tuple[int, int]) -> tuple[int, int]:
    return (t[0] + (t[1] == 12), (t[1] % 12) + 1)


def _iter_months(a: tuple[int, int], b: tuple[int, int]):
    cur = a
    while cur <= b:
        yield f"{cur[0]:04d}-{cur[1]:02d}"
        cur = _next_month(cur)


def _apply_txn_filters(query, user, date_from, date_to, account_id, category,
                       db):
    query = query.where(Transaction.user_id == user.id)
    if date_from:
        query = query.where(Transaction.occurred_on >= date_from)
    if date_to:
        query = query.where(Transaction.occurred_on <= date_to)
    if account_id is not None:
        query = query.where(
            or_(Transaction.from_account_id == account_id,
                Transaction.to_account_id == account_id)
        )
    if category:
        query = query.where(func.lower(Transaction.category) == category.lower())
    return query


def _signed_delta(t: Transaction, account_id: int | None) -> int:
    """Change to the (possibly single-account) balance from one transaction.
    Across all accounts transfers are zero-sum; for one account they move money
    in or out, so the sign depends on which side the account is on."""
    if account_id is None:
        if t.type == "income":
            return t.amount_minor
        if t.type == "expense":
            return -t.amount_minor
        return 0  # transfer nets to zero across all accounts
    if t.type == "income" and t.to_account_id == account_id:
        return t.amount_minor
    if t.type == "expense" and t.from_account_id == account_id:
        return -t.amount_minor
    if t.type == "transfer":
        if t.to_account_id == account_id:
            return t.amount_minor
        if t.from_account_id == account_id:
            return -t.amount_minor
    return 0


def _balance_history(db: Session, user: User, account_id: int | None,
                     date_from: date | None, date_to: date | None):
    if account_id is not None:
        accounts = [get_owned(db, Account, account_id, user.id)]
        accounts = [a for a in accounts if a.initialized]
    else:
        accounts = [
            a for a in db.scalars(
                select(Account).where(Account.user_id == user.id)
            ).all() if a.initialized
        ]

    if not accounts:
        return BalanceHistory(
            available=False, starting_balance_minor=None, points=[],
            note="No initialized account balance, so history is unknown.",
        )

    starting = sum(a.initial_balance_minor for a in accounts)

    txns = db.scalars(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.occurred_on, Transaction.id)
    ).all()
    month_net: dict[str, int] = defaultdict(int)
    for t in txns:
        delta = _signed_delta(t, account_id)
        if delta:
            month_net[_month_str(t.occurred_on)] += delta

    today = date_to or date.today()
    end_month = _month_tuple(_month_str(today))
    if date_from:
        start_month = _month_tuple(_month_str(date_from))
    elif month_net:
        start_month = _month_tuple(min(month_net))
    else:
        start_month = end_month

    # Accumulate from the earliest data (or start) so running balance is exact.
    acc_start = start_month
    if month_net:
        first_data = _month_tuple(min(month_net))
        acc_start = min(start_month, first_data)

    running = starting
    points = []
    for m in _iter_months(acc_start, end_month):
        running += month_net.get(m, 0)
        if _month_tuple(m) >= start_month:
            points.append(BalancePoint(
                month=m, net_change_minor=month_net.get(m, 0),
                running_balance_minor=running,
            ))

    return BalanceHistory(
        available=True, starting_balance_minor=starting, points=points, note=None
    )


def _shortage(db: Session, user: User) -> ShortageReport:
    items = db.scalars(
        select(InventoryItem).where(
            InventoryItem.user_id == user.id, InventoryItem.deleted_at.is_(None)
        )
    ).all()
    below = [i for i in items if i.target_quantity is not None
             and i.quantity_owned < i.target_quantity]
    price_needed = [i for i in below if i.estimated_unit_cost_minor is None]
    cost = sum((i.target_quantity - i.quantity_owned) * i.estimated_unit_cost_minor
               for i in below if i.estimated_unit_cost_minor is not None)
    return ShortageReport(
        items_below_target=len(below),
        price_needed_items=len(price_needed),
        # Null when any shortfall is unpriced, else the real estimate (0 ok).
        estimated_cost_minor=None if price_needed else (cost if below else 0),
    )


def _goals_report(db: Session, user: User) -> list[GoalProgress]:
    goals = db.scalars(
        select(Goal).where(Goal.user_id == user.id)
        .order_by(Goal.status, Goal.created_at.desc())
    ).all()
    out = []
    for g in goals:
        percent = None
        remaining_amount = None
        remaining_quantity = None
        if g.type == "money" and g.target_amount_minor:
            saved = db.scalar(
                select(func.coalesce(func.sum(GoalContribution.amount_minor), 0)).where(
                    GoalContribution.goal_id == g.id
                )
            ) or 0
            remaining_amount = max(g.target_amount_minor - saved, 0)
            percent = min(int(saved * 100 / g.target_amount_minor), 100)
        elif g.type == "quantity" and g.target_quantity:
            current = g.current_quantity or 0
            remaining_quantity = max(g.target_quantity - current, 0)
            percent = min(int(current * 100 / g.target_quantity), 100)
        out.append(GoalProgress(
            id=g.id, name=g.name, type=g.type, status=g.status,
            percent=percent, remaining_amount_minor=remaining_amount,
            remaining_quantity=remaining_quantity,
        ))
    return out


def _obligations(db: Session, user: User, date_to: date | None) -> ObligationsReport:
    today = date.today()
    cutoff = date_to or today
    items: list[ObligationItem] = []
    outstanding_fees = 0
    overdue = 0

    fees = db.scalars(
        select(FeeObligation).where(
            FeeObligation.user_id == user.id, FeeObligation.deleted_at.is_(None)
        )
    ).all()
    for f in fees:
        outstanding = max(f.amount_due_minor - f.amount_paid_minor, 0)
        if outstanding <= 0:
            continue
        outstanding_fees += outstanding
        status = "unpaid" if f.amount_paid_minor == 0 else "partial"
        if f.due_on and f.due_on < today:
            status = "overdue"
            overdue += 1
        items.append(ObligationItem(
            name=f.name, kind="fee", due_on=f.due_on,
            outstanding_minor=outstanding, status=status,
        ))

    goals = db.scalars(
        select(Goal).where(
            Goal.user_id == user.id, Goal.status == "active",
            Goal.deadline.isnot(None),
        )
    ).all()
    for g in goals:
        if g.deadline > cutoff:
            continue
        status = "overdue" if g.deadline < today else "upcoming"
        if status == "overdue":
            overdue += 1
        items.append(ObligationItem(
            name=g.name, kind="goal", due_on=g.deadline,
            outstanding_minor=None, status=status,
        ))

    items.sort(key=lambda i: (i.due_on or date.max, i.kind))
    return ObligationsReport(
        outstanding_fees_minor=outstanding_fees, overdue_count=overdue, items=items
    )


def _build_summary(db: Session, user: User, date_from, date_to, account_id,
                   category) -> ReportSummary:
    account_name = None
    if account_id is not None:
        account_name = get_owned(db, Account, account_id, user.id).name

    txns = db.scalars(
        _apply_txn_filters(select(Transaction), user, date_from, date_to,
                           account_id, category, db)
    ).all()

    income = expense = transfers = 0
    by_cat: dict[str, dict] = defaultdict(lambda: {"total": 0, "count": 0})
    for t in txns:
        if t.type == "income":
            income += t.amount_minor
        elif t.type == "expense":
            expense += t.amount_minor
            key = (t.category or "Uncategorized").title()
            by_cat[key]["total"] += t.amount_minor
            by_cat[key]["count"] += 1
        else:
            transfers += t.amount_minor

    spending = sorted(
        (CategorySpend(category=k, total_minor=v["total"], count=v["count"])
         for k, v in by_cat.items()),
        key=lambda c: c.total_minor, reverse=True,
    )

    total_saved = db.scalar(
        select(func.coalesce(func.sum(GoalContribution.amount_minor), 0)).where(
            GoalContribution.user_id == user.id
        )
    ) or 0
    saved_q = select(func.coalesce(func.sum(GoalContribution.amount_minor), 0)).where(
        GoalContribution.user_id == user.id
    )
    if date_from:
        saved_q = saved_q.where(GoalContribution.occurred_on >= date_from)
    if date_to:
        saved_q = saved_q.where(GoalContribution.occurred_on <= date_to)
    saved_in_period = db.scalar(saved_q) or 0
    active_goals = db.scalar(
        select(func.count(Goal.id)).where(Goal.user_id == user.id,
                                          Goal.status == "active")
    ) or 0
    completed_goals = db.scalar(
        select(func.count(Goal.id)).where(Goal.user_id == user.id,
                                          Goal.status == "completed")
    ) or 0

    biz_q = select(BusinessRecord).where(BusinessRecord.user_id == user.id)
    if date_from:
        biz_q = biz_q.where(BusinessRecord.occurred_on >= date_from)
    if date_to:
        biz_q = biz_q.where(BusinessRecord.occurred_on <= date_to)
    if category:
        biz_q = biz_q.where(func.lower(BusinessRecord.category) == category.lower())
    revenue = expenses = 0
    for r in db.scalars(biz_q).all():
        if r.type == "revenue":
            revenue += r.amount_minor
        elif r.type == "expense":
            expenses += r.amount_minor

    return ReportSummary(
        period=ReportPeriod(
            date_from=date_from, date_to=date_to, account_id=account_id,
            account_name=account_name, category=category,
        ),
        currency=user.currency,
        cash_flow=CashFlow(
            income_minor=income, expense_minor=expense, net_minor=income - expense,
            transfers_minor=transfers, txn_count=len(txns),
        ),
        spending_by_category=spending,
        balance_history=_balance_history(db, user, account_id, date_from, date_to),
        savings=SavingsProgress(
            total_saved_in_goals_minor=total_saved,
            saved_in_period_minor=saved_in_period,
            active_goals=active_goals, completed_goals=completed_goals,
        ),
        goals=_goals_report(db, user),
        shortage=_shortage(db, user),
        business=BusinessReport(
            revenue_minor=revenue, expenses_minor=expenses,
            net_profit_minor=revenue - expenses,
        ),
        obligations=_obligations(db, user, date_to),
        note=("Transfers are excluded from income/expense and net. Unknown "
              "balances and unpriced shortages are shown as unknown, never zero. "
              "Fees count as paid only up to recorded payments."),
    )


@router.get("/summary", response_model=ReportSummary)
def summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    account_id: int | None = Query(default=None),
    category: str | None = Query(default=None, max_length=80),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _build_summary(db, user, date_from, date_to, account_id, category)


def _major(minor: int) -> str:
    return f"{minor // 100}.{minor % 100:02d}"


@router.get("/export.csv")
def export_csv(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    account_id: int | None = Query(default=None),
    category: str | None = Query(default=None, max_length=80),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Ledger export honoring the same filters - raw saved records, no figures
    invented. Money written in major units with two decimals (integer-safe)."""
    q = _apply_txn_filters(
        select(Transaction), user, date_from, date_to, account_id, category, db
    ).order_by(Transaction.occurred_on, Transaction.id)
    rows = db.scalars(q).all()

    buf = StringIO()
    w = csv_writer(buf)
    w.writerow(["date", "type", "category", "description", "amount", "currency"])
    for t in rows:
        w.writerow([
            t.occurred_on.isoformat(), t.type, t.category or "",
            t.description or "", _major(t.amount_minor), t.currency,
        ])

    filename = "lifesmart-report.csv"
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
