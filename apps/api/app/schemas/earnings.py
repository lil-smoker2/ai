"""Savings & Earnings contracts.

Money is integer minor units. Income sources carry *expected* amounts used for
planning only; business records are confirmed figures. The forecast separates
confirmed balances/records from expected planning values and states its
assumptions. A savings vehicle carries a rate the person was quoted and the
date they checked it - this app has no network connection, so it cannot know
any platform's current rate and never claims to.
"""
import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

INCOME_FREQUENCIES = ("daily", "weekly", "monthly", "yearly", "once")
INCOME_RELIABILITY = ("uncertain", "likely", "confirmed")
BUSINESS_RECORD_TYPES = ("revenue", "expense")
VEHICLE_KINDS = (
    "mpesa",
    "bank",
    "sacco",
    "money_market",
    "shares",
    "betting",
    "other",
)
VEHICLE_FLOW_DIRECTIONS = ("in", "out")
# Products that quote an annual rate the person can write down.
INTEREST_KINDS = ("mpesa", "bank", "sacco", "money_market", "other")
# Things held in units and priced by whoever last looked.
HOLDING_KINDS = ("shares",)
# A gamble: no rate exists to project from, so no rate field is offered.
RISK_KINDS = ("betting",)

# An external link is rendered and handed to the real browser, so only http(s)
# is accepted - never javascript: or anything else that runs.
_URL = re.compile(r"^https?://[^\s<>\"'`]+$")


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


# --- Savings vehicles: the places money can sit -------------------------------


def clean_vehicle_url(raw: str | None) -> str | None:
    """Accept a real web address or nothing at all."""
    if raw is None or not raw.strip():
        return None
    value = raw.strip()
    if not _URL.match(value):
        raise ValueError("Link must be a full web address starting with https://")
    return value[:300]


def normalize_vehicle_details(
    kind: str,
    rate_percent: float | None,
    rate_checked_on: date | None,
    units: float | None,
    value_minor: int | None,
    valued_on: date | None,
) -> tuple[float | None, date | None, float | None, int | None, date | None]:
    """Keep only what this kind of vehicle can honestly carry.

    Shared by creation and correction so the same question cannot be judged two
    ways. A percentage without the day it was checked is refused rather than
    stored, because an undated rate is exactly the number that gets read as
    current a year later, and nothing here can refresh it. A holding's value
    needs its date for the same reason.

    A betting site keeps none of it: no percentage can be projected from a
    gamble, so offering the field would promise what nobody can promise.
    """
    if kind in RISK_KINDS:
        return None, None, None, None, None
    if kind in HOLDING_KINDS:
        if value_minor is not None and valued_on is None:
            raise ValueError(
                "Say when a holding was valued. A price without a date is a "
                "guess about today."
            )
        # Shares pay no quoted annual rate, so no rate is kept on them.
        return None, None, units, value_minor, valued_on
    if rate_percent is not None and rate_checked_on is None:
        raise ValueError(
            "A rate needs the date you checked it. LifeSmart cannot look a "
            "platform's rate up, so an undated percentage is unverifiable."
        )
    if rate_percent is None:
        # A date with no rate dates nothing.
        return None, None, None, None, None
    return rate_percent, rate_checked_on, None, None, None


class VehicleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(pattern=f"^({'|'.join(VEHICLE_KINDS)})$")
    url: str | None = Field(default=None, max_length=300)
    rate_percent: float | None = Field(default=None, gt=0, le=100)
    rate_checked_on: date | None = None
    units: float | None = Field(default=None, gt=0)
    value_minor: int | None = Field(default=None, ge=0)
    valued_on: date | None = None
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def check_details(self) -> "VehicleCreate":
        (
            self.rate_percent,
            self.rate_checked_on,
            self.units,
            self.value_minor,
            self.valued_on,
        ) = normalize_vehicle_details(
            self.kind,
            self.rate_percent,
            self.rate_checked_on,
            self.units,
            self.value_minor,
            self.valued_on,
        )
        return self

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Give the place you keep money a name")
        return cleaned[:120]

    @field_validator("url")
    @classmethod
    def check_url(cls, v: str | None) -> str | None:
        return clean_vehicle_url(v)


class VehicleUpdate(VehicleCreate):
    """The whole card sent again, as the Add form sends it.

    Unlike an account correction, every field is expected: the edit form shows
    them all, so leaving a rate out means "remove it" rather than "keep it".
    """


class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    url: str | None
    rate_percent: float | None
    rate_checked_on: date | None
    units: float | None
    value_minor: int | None
    valued_on: date | None
    notes: str | None
    created_at: datetime
    # From the flow records. put_in / taken_out are 0 when nothing was ever
    # recorded, which net_in distinguishes by staying null: no record is not a
    # record of nothing.
    put_in_minor: int = 0
    taken_out_minor: int = 0
    net_in_minor: int | None = None
    # A holding's worth against what was put in: only when a value was entered.
    gain_minor: int | None = None


class VehicleFlowCreate(BaseModel):
    direction: str = Field(pattern=f"^({'|'.join(VEHICLE_FLOW_DIRECTIONS)})$")
    amount_minor: int = Field(gt=0)
    occurred_on: date
    note: str | None = Field(default=None, max_length=255)


class VehicleFlowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: int
    direction: str
    amount_minor: int
    occurred_on: date
    note: str | None
    created_at: datetime


class ProjectionCreate(BaseModel):
    """What to imagine saving, and for how long. Nothing is recorded."""

    amount_minor: int = Field(gt=0)
    months: int = Field(ge=1, le=600)


class Projection(BaseModel):
    amount_minor: int
    months: int
    rate_percent: float
    rate_checked_on: date | None
    interest_minor: int
    total_minor: int
    # Says out loud what the figure rests on, so it cannot be read as a quote.
    assumptions: list[str]
