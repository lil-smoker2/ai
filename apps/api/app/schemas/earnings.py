"""Savings & Earnings contracts.

Money is integer minor units. Income sources carry *expected* amounts used for
planning only; business records are confirmed figures. The forecast separates
confirmed balances/records from expected planning values and states its
assumptions.
"""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

INCOME_FREQUENCIES = ("daily", "weekly", "monthly", "yearly", "once")
INCOME_RELIABILITY = ("uncertain", "likely", "confirmed")
BUSINESS_RECORD_TYPES = ("revenue", "expense")


class IncomeSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expected_amount_minor: int = Field(gt=0)
    frequency: str = Field(default="monthly", pattern=f"^({'|'.join(INCOME_FREQUENCIES)})$")
    next_expected_date: date | None = None
    reliability: str = Field(default="likely", pattern=f"^({'|'.join(INCOME_RELIABILITY)})$")
    active: bool = True
    notes: str | None = None


class IncomeSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    expected_amount_minor: int | None = Field(default=None, gt=0)
    frequency: str | None = Field(default=None, pattern=f"^({'|'.join(INCOME_FREQUENCIES)})$")
    next_expected_date: date | None = None
    reliability: str | None = Field(default=None, pattern=f"^({'|'.join(INCOME_RELIABILITY)})$")
    active: bool | None = None
    notes: str | None = None


class IncomeSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    expected_amount_minor: int
    frequency: str
    next_expected_date: date | None
    reliability: str
    active: bool
    notes: str | None
    created_at: datetime
    # Expected amount normalized to a per-month planning figure (not received).
    monthly_expected_minor: int = 0


class BusinessRecordCreate(BaseModel):
    business_name: str = Field(min_length=1, max_length=120)
    type: str = Field(pattern=f"^({'|'.join(BUSINESS_RECORD_TYPES)})$")
    amount_minor: int = Field(gt=0)
    category: str | None = Field(default=None, max_length=80)
    occurred_on: date | None = None
    transaction_id: int | None = None
    notes: str | None = None


class BusinessRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_name: str
    type: str
    amount_minor: int
    category: str | None
    occurred_on: date
    transaction_id: int | None
    notes: str | None
    created_at: datetime


class BusinessProfit(BaseModel):
    """net_business_profit = revenue - expenses, per business and total."""

    business_name: str
    revenue_minor: int
    expenses_minor: int
    net_profit_minor: int


class EarningsSummary(BaseModel):
    # Confirmed, recorded balance across initialized accounts (null if unknown).
    recorded_available_balance_minor: int | None
    # Expected recurring income per month from ACTIVE income sources only.
    monthly_expected_income_minor: int
    # Confirmed business figures for the current month.
    business_revenue_this_month_minor: int
    business_expenses_this_month_minor: int
    business_net_profit_this_month_minor: int
    # Confirmed savings contributions this month and total saved across goals.
    savings_contributed_this_month_minor: int
    total_saved_in_goals_minor: int
    # Outstanding remaining across active money goals (a committed obligation).
    outstanding_obligations_minor: int
    # Planning estimate = balance + monthly expected income - outstanding.
    # Null when the balance is not initialized (never a fake zero).
    available_for_planning_minor: int | None
    assumptions: list[str]
