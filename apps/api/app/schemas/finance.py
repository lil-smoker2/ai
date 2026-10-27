from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import Page

ACCOUNT_TYPES = ("cash", "mpesa", "bank", "wallet", "custom")
TRANSACTION_TYPES = ("income", "expense", "transfer")


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(pattern=f"^({'|'.join(ACCOUNT_TYPES)})$")


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    is_synced: bool
    initialized: bool
    initial_balance_minor: int
    created_at: datetime
    # None until explicitly initialized - never treated as a known zero.
    balance_minor: int | None = None


class AccountInitialize(BaseModel):
    balance_minor: int = Field(ge=0)


class BalanceSummary(BaseModel):
    total_available_minor: int | None
    initialized_accounts: int
    uninitialized_accounts: int


class TransactionCreate(BaseModel):
    type: str = Field(pattern=f"^({'|'.join(TRANSACTION_TYPES)})$")
    amount_minor: int = Field(gt=0)
    currency: str = Field(default="KES", pattern=r"^[A-Z]{3}$")
    occurred_on: date
    category: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    account_id: int | None = None
    from_account_id: int | None = None
    to_account_id: int | None = None
    goal_id: int | None = None
    reference: str | None = Field(default=None, max_length=120)
    idempotency_key: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def check_accounts(self) -> "TransactionCreate":
        if self.type == "income" and self.account_id is None:
            raise ValueError("income requires account_id")
        if self.type == "expense" and self.account_id is None:
            raise ValueError("expense requires account_id")
        if self.type == "transfer":
            if self.from_account_id is None or self.to_account_id is None:
                raise ValueError("transfer requires from_account_id and to_account_id")
            if self.from_account_id == self.to_account_id:
                raise ValueError("transfer accounts must differ")
        return self


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    amount_minor: int
    currency: str
    occurred_on: date
    category: str | None
    description: str | None
    from_account_id: int | None
    to_account_id: int | None
    goal_id: int | None
    reference: str | None
    reversed: bool
    reversal_of_id: int | None
    created_at: datetime


class TransactionPage(BaseModel):
    transactions: list[TransactionOut]
    page: Page


class MonthSummary(BaseModel):
    income_minor: int
    expense_minor: int
    # Transfers are excluded from income/expenses by design.
    transfers_minor: int
