"""Student Life contracts: fees, payments, accommodation and food budget.

Money is integer minor units. Fee status (paid/partial/unpaid) is derived from
recorded payments, never stored as a claim. Unknown prices stay null.
"""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

FEE_CATEGORIES = ("tuition", "registration", "other")
HOSTEL_STATUSES = ("unchecked", "available", "taken", "booked")

_FEE_CAT_RE = f"^({'|'.join(FEE_CATEGORIES)})$"
_HOSTEL_RE = f"^({'|'.join(HOSTEL_STATUSES)})$"


class FeeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="tuition", pattern=_FEE_CAT_RE)
    amount_due_minor: int = Field(gt=0)
    due_on: date | None = None
    reference: str | None = Field(default=None, max_length=120)
    goal_id: int | None = None
    notes: str | None = None


class FeeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, pattern=_FEE_CAT_RE)
    amount_due_minor: int | None = Field(default=None, gt=0)
    due_on: date | None = None
    reference: str | None = Field(default=None, max_length=120)
    goal_id: int | None = None
    notes: str | None = None


class FeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    amount_due_minor: int
    amount_paid_minor: int
    due_on: date | None
    reference: str | None
    goal_id: int | None
    notes: str | None
    created_at: datetime
    # Derived from amounts only.
    outstanding_minor: int = 0
    status: str = "unpaid"  # unpaid | partial | paid


class FeePaymentCreate(BaseModel):
    amount_minor: int = Field(gt=0)
    occurred_on: date | None = None
    account_id: int | None = None
    reference: str | None = Field(default=None, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=64)


class FeePaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fee_id: int
    amount_minor: int
    occurred_on: date
    transaction_id: int | None
    reference: str | None
    idempotency_key: str
    created_at: datetime


class HostelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=160)
    monthly_rent_minor: int | None = Field(default=None, ge=0)
    deposit_minor: int | None = Field(default=None, ge=0)
    facilities: str | None = None
    booking_source: str | None = Field(default=None, max_length=160)
    notes: str | None = None


class HostelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=160)
    monthly_rent_minor: int | None = Field(default=None, ge=0)
    deposit_minor: int | None = Field(default=None, ge=0)
    facilities: str | None = None
    booking_source: str | None = Field(default=None, max_length=160)
    notes: str | None = None


class HostelAvailabilityUpdate(BaseModel):
    status: str = Field(pattern=_HOSTEL_RE)


class HostelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str | None
    monthly_rent_minor: int | None
    deposit_minor: int | None
    status: str
    facilities: str | None
    booking_source: str | None
    last_checked_at: datetime | None
    notes: str | None
    created_at: datetime


class FoodBudgetUpdate(BaseModel):
    weekly_budget_minor: int | None = Field(default=None, ge=0)
    monthly_budget_minor: int | None = Field(default=None, ge=0)
    period: str | None = Field(default=None, pattern="^(weekly|monthly)$")
    notes: str | None = None


class FoodBudgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    weekly_budget_minor: int | None
    monthly_budget_minor: int | None
    period: str | None
    notes: str | None
    updated_at: datetime
    # Derived planning figures; null when no weekly budget is set.
    daily_estimate_minor: int | None = None


class FoodStockCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    quantity_bought: float = Field(gt=0)
    unit: str = Field(default="kg")
    quantity_per_day: float = Field(gt=0)
    purchase_date: date | None = None
    notes: str | None = None


class FoodStockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    quantity_bought: float
    unit: str
    quantity_per_day: float
    purchase_date: date
    notes: str | None
    created_at: datetime
    days_remaining: float | None = None
    depletion_date: date | None = None


class StudentSummary(BaseModel):
    total_fees_due_minor: int
    total_fees_paid_minor: int
    total_fees_outstanding_minor: int
    overdue_fees_count: int
    hostel_options_count: int
