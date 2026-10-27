"""Reports contracts.

Every figure is derived from saved records over an optional window/filters.
Unknown values stay null (never a fabricated zero): an uninitialized balance,
an unpriced shortage, or a goal without a target all report as unknown rather
than as a real number.
"""
from datetime import date

from pydantic import BaseModel


class ReportPeriod(BaseModel):
    date_from: date | None
    date_to: date | None
    account_id: int | None
    account_name: str | None
    category: str | None


class CashFlow(BaseModel):
    income_minor: int
    expense_minor: int
    # net = income - expense; transfers are excluded by design.
    net_minor: int
    transfers_minor: int
    txn_count: int


class CategorySpend(BaseModel):
    category: str
    total_minor: int
    count: int


class BalancePoint(BaseModel):
    month: str  # YYYY-MM
    net_change_minor: int
    running_balance_minor: int


class BalanceHistory(BaseModel):
    # False when no account has an initialized balance: history is unknown.
    available: bool
    starting_balance_minor: int | None
    points: list[BalancePoint]
    note: str | None


class SavingsProgress(BaseModel):
    total_saved_in_goals_minor: int
    saved_in_period_minor: int
    active_goals: int
    completed_goals: int


class GoalProgress(BaseModel):
    id: int
    name: str
    type: str
    status: str
    # Null when the goal has no measurable target (custom/obligation).
    percent: int | None
    remaining_amount_minor: int | None
    remaining_quantity: int | None


class ShortageReport(BaseModel):
    items_below_target: int
    price_needed_items: int
    # Null when any shortfall lacks a price - never a guessed total.
    estimated_cost_minor: int | None


class BusinessReport(BaseModel):
    revenue_minor: int
    expenses_minor: int
    net_profit_minor: int


class ObligationItem(BaseModel):
    name: str
    kind: str  # fee | goal
    due_on: date | None
    outstanding_minor: int | None
    status: str


class ObligationsReport(BaseModel):
    outstanding_fees_minor: int
    overdue_count: int
    items: list[ObligationItem]


class ReportSummary(BaseModel):
    period: ReportPeriod
    currency: str
    cash_flow: CashFlow
    spending_by_category: list[CategorySpend]
    balance_history: BalanceHistory
    savings: SavingsProgress
    goals: list[GoalProgress]
    shortage: ShortageReport
    business: BusinessReport
    obligations: ObligationsReport
    note: str
