import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import Page

ACCOUNT_TYPES = ("cash", "mpesa", "mshwari", "bank", "wallet", "custom")
TRANSACTION_TYPES = ("income", "expense", "transfer")
# Account types that are identified by a Safaricom phone number.
MPESA_TYPES = ("mpesa", "mshwari")

# A Kenyan Safaricom line: 07XX XXX XXX, the newer 01XX prefixes, or the same
# thing spelled out as 2547... / +2547...
_PHONE = re.compile(r"^(?:\+?254|0)([17])\d{8}$")
_ACCOUNT_NUMBER = re.compile(r"^[0-9A-Za-z-]{4,30}$")


def normalize_mpesa_number(raw: str) -> str:
    """Return a Safaricom number as +254XXXXXXXXX, or raise a clear message.

    Only the shape is checked. Nothing here confirms the number exists, is
    yours, or has any balance - LifeSmart cannot query M-PESA.
    """
    compact = re.sub(r"[\s\-()]", "", raw.strip())
    match = _PHONE.match(compact)
    if not match:
        raise ValueError(
            "M-PESA number not recognised. Use the local form, e.g. "
            "0712 345 678 or +254712345678."
        )
    return f"+254{match.group(1)}{compact[-8:]}"


def clean_account_name(raw: str) -> str:
    """Trim a name to what is worth storing, or raise if nothing was typed."""
    cleaned = raw.strip()
    if not cleaned:
        raise ValueError("Account name cannot be blank")
    return cleaned[:120]


def normalize_account_details(
    kind: str,
    mpesa_number: str | None,
    bank_name: str | None,
    account_number: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Return the details this kind of account can hold, or raise a clear message.

    Used both when an account is created and when it is corrected, so the same
    question cannot be judged two different ways. Only the shape is checked -
    nothing here knows the number exists or is the person's own.

    Details belonging to some other kind of account are dropped rather than
    kept, so an M-PESA number cannot survive on what has become a bank account.
    """
    if kind in MPESA_TYPES:
        if not mpesa_number:
            raise ValueError(
                "M-Shwari is saved on an M-PESA line, so that phone number "
                "is needed."
                if kind == "mshwari"
                else "An M-PESA account needs the phone number it is held on."
            )
        return normalize_mpesa_number(mpesa_number), None, None
    if kind == "bank":
        name = (bank_name or "").strip()
        if len(name) < 2:
            raise ValueError("A bank account needs the bank's name.")
        number = (account_number or "").strip().replace(" ", "")
        if not _ACCOUNT_NUMBER.match(number):
            raise ValueError(
                "Bank account number should be 4-30 digits, letters or "
                "dashes, with no other characters."
            )
        return None, name[:80], number
    return None, None, None


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(pattern=f"^({'|'.join(ACCOUNT_TYPES)})$")
    # Details belong to the type that was chosen. A number typed against the
    # wrong kind of account is dropped rather than stored somewhere misleading.
    mpesa_number: str | None = Field(default=None, max_length=20)
    bank_name: str | None = Field(default=None, max_length=80)
    account_number: str | None = Field(default=None, max_length=30)
    # Typed once, at creation, when the person already knows what they hold.
    # Absent stays unknown: it is not recorded as a zero balance.
    balance_minor: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_details(self) -> "AccountCreate":
        (
            self.mpesa_number,
            self.bank_name,
            self.account_number,
        ) = normalize_account_details(
            self.type, self.mpesa_number, self.bank_name, self.account_number
        )
        return self

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return clean_account_name(v)


class AccountUpdate(BaseModel):
    """Correct an account that already exists. Every field is optional.

    A field left out keeps the value stored on it, which is decided against the
    database row in the API rather than here - a schema cannot see what is
    already saved. So renaming an account does not demand its phone number
    again, while changing its kind has to bring whatever the new kind needs:
    a bank account with no bank behind it is nothing to record.
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    # Optional unlike on creation: leaving it out means "stay the same kind".
    type: str | None = Field(default=None, pattern=f"^({'|'.join(ACCOUNT_TYPES)})$")
    mpesa_number: str | None = Field(default=None, max_length=20)
    bank_name: str | None = Field(default=None, max_length=80)
    account_number: str | None = Field(default=None, max_length=30)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return None if v is None else clean_account_name(v)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    mpesa_number: str | None = None
    bank_name: str | None = None
    account_number: str | None = None
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


class ExpenseAnomalyOut(BaseModel):
    """One expense judged unusual against its own category's recorded median."""

    transaction_id: int
    description: str | None
    category: str
    amount_minor: int
    currency: str
    occurred_on: date
    category_median_minor: int
    deviation_score: float


class ExpenseAnomaliesOut(BaseModel):
    generated_on: date
    window_days: int
    min_category_expenses: int
    anomalies: list[ExpenseAnomalyOut]
