"""Money API: accounts, transactions, transfers, reversals, balances.

All amounts are integer minor units. Transfers move funds between accounts and
are never counted as income or expense. Balances derive only from saved
records; uninitialized accounts have unknown (not zero) balances.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned
from app.core.database import get_db
from app.models.finance import Account, Transaction
from app.models.user import User
from app.schemas.common import Page
from app.schemas.finance import (
    AccountCreate,
    AccountInitialize,
    AccountOut,
    AccountUpdate,
    BalanceSummary,
    ExpenseAnomaliesOut,
    MonthSummary,
    TransactionCreate,
    TransactionOut,
    TransactionPage,
    normalize_account_details,
)
from app.services import anomalies as anomaly_service

router = APIRouter(prefix="/api", tags=["money"])


def _account_balance(db: Session, account: Account) -> int | None:
    if not account.initialized:
        return None
    incoming = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount_minor), 0)).where(
            Transaction.to_account_id == account.id,
            Transaction.user_id == account.user_id,
        )
    )
    outgoing = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount_minor), 0)).where(
            Transaction.from_account_id == account.id,
            Transaction.user_id == account.user_id,
        )
    )
    return account.initial_balance_minor + incoming - outgoing


def _account_out(db: Session, account: Account) -> AccountOut:
    out = AccountOut.model_validate(account)
    out.balance_minor = _account_balance(db, account)
    return out


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    accounts = db.scalars(
        select(Account).where(Account.user_id == user.id).order_by(Account.created_at)
    ).all()
    return [_account_out(db, a) for a in accounts]


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(body: AccountCreate, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """Create one account.

    The type-specific details have already been validated and normalized by the
    schema. A balance given here marks the account initialized; a balance left
    out stays unknown rather than becoming zero, so the Money page can tell the
    two apart. is_synced is never set: an M-PESA or bank number typed by the
    person identifies the account, it does not connect to one.
    """
    account = Account(
        user_id=user.id,
        name=body.name,
        type=body.type,
        mpesa_number=body.mpesa_number,
        bank_name=body.bank_name,
        account_number=body.account_number,
    )
    if body.balance_minor is not None:
        account.initialized = True
        account.initial_balance_minor = body.balance_minor
    db.add(account)
    db.commit()
    return _account_out(db, account)


@router.post("/accounts/{account_id}/initialize", response_model=AccountOut)
def initialize_account(account_id: int, body: AccountInitialize,
                       db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    account = get_owned(db, Account, account_id, user.id)
    account.initialized = True
    account.initial_balance_minor = body.balance_minor
    db.commit()
    return _account_out(db, account)


def _kept(sent: str | None, stored: str | None) -> str | None:
    """Resolve an optional field against what is already stored.

    Sending a field and leaving it out are different requests: a field typed
    over replaces the stored value, even with blanks, while one absent from the
    body keeps it. So renaming an account does not have to resend its number.
    """
    return stored if sent is None else sent


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def update_account(account_id: int, body: AccountUpdate,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """Correct an account instead of deleting it, so its money stays put.

    A balance is the initial figure plus the transactions naming this account,
    so neither a rename nor a change of kind can move a pesa: an account added
    by mistake as M-PESA and corrected to a bank still holds what it held.
    Fields left out keep what was stored, and the rules for the kind are the
    ones applied at creation, run against the details as they would stand
    afterwards. is_synced is never touched here - editing a number is still a
    note about an account, not a connection to one.
    """
    account = get_owned(db, Account, account_id, user.id)
    kind = body.type or account.type
    try:
        mpesa_number, bank_name, account_number = normalize_account_details(
            kind,
            _kept(body.mpesa_number, account.mpesa_number),
            _kept(body.bank_name, account.bank_name),
            _kept(body.account_number, account.account_number),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if body.name is not None:
        account.name = body.name
    account.type = kind
    account.mpesa_number = mpesa_number
    account.bank_name = bank_name
    account.account_number = account_number
    db.commit()
    return _account_out(db, account)


@router.get("/accounts/summary", response_model=BalanceSummary)
def balance_summary(db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    accounts = db.scalars(select(Account).where(Account.user_id == user.id)).all()
    initialized = [a for a in accounts if a.initialized]
    uninitialized = [a for a in accounts if not a.initialized]
    total = None
    if initialized:
        total = sum(_account_balance(db, a) for a in initialized)
    return BalanceSummary(
        total_available_minor=total,
        initialized_accounts=len(initialized),
        uninitialized_accounts=len(uninitialized),
    )


@router.post("/transactions", response_model=TransactionOut, status_code=201)
def create_transaction(body: TransactionCreate, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    # Idempotency: repeated requests with the same key return the first record.
    if body.idempotency_key:
        existing = db.scalars(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.idempotency_key == body.idempotency_key,
            )
        ).first()
        if existing:
            return existing

    from_id = to_id = None
    if body.type == "income":
        to_id = get_owned(db, Account, body.account_id, user.id).id
    elif body.type == "expense":
        from_id = get_owned(db, Account, body.account_id, user.id).id
    else:  # transfer
        from_id = get_owned(db, Account, body.from_account_id, user.id).id
        to_id = get_owned(db, Account, body.to_account_id, user.id).id

    if body.goal_id is not None:
        from app.models.goal import Goal

        get_owned(db, Goal, body.goal_id, user.id)

    txn = Transaction(
        user_id=user.id,
        type=body.type,
        amount_minor=body.amount_minor,
        currency=body.currency,
        occurred_on=body.occurred_on,
        category=body.category,
        description=body.description,
        from_account_id=from_id,
        to_account_id=to_id,
        goal_id=body.goal_id,
        reference=body.reference,
        idempotency_key=body.idempotency_key,
    )
    db.add(txn)
    db.commit()
    return txn


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    account_id: int | None = Query(default=None),
    type: str | None = Query(default=None, pattern="^(income|expense|transfer)$"),
    category: str | None = Query(default=None, max_length=80),
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Transaction).where(Transaction.user_id == user.id)
    if date_from:
        query = query.where(Transaction.occurred_on >= date_from)
    if date_to:
        query = query.where(Transaction.occurred_on <= date_to)
    if account_id is not None:
        get_owned(db, Account, account_id, user.id)
        query = query.where(
            or_(Transaction.from_account_id == account_id,
                Transaction.to_account_id == account_id)
        )
    if type:
        query = query.where(Transaction.type == type)
    if category:
        query = query.where(func.lower(Transaction.category) == category.lower())
    if search:
        query = query.where(func.lower(Transaction.description).contains(search.lower()))

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(Transaction.occurred_on.desc(), Transaction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return TransactionPage(
        transactions=rows,
        page=Page(total=total, page=page, page_size=page_size),
    )


@router.get("/transactions/anomalies", response_model=ExpenseAnomaliesOut)
def expense_anomalies(db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Expenses that stand out against their own category's recent middle.

    Recomputed from saved transactions on every call; a category too thin to
    have a dependable median reports nothing. Declared ahead of the integer
    /transactions/{transaction_id} route so the literal path is not swallowed
    by the id parameter."""
    return anomaly_service.find_expense_anomalies(db, user)


@router.get("/transactions/{transaction_id}", response_model=TransactionOut)
def get_transaction(transaction_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return get_owned(db, Transaction, transaction_id, user.id)


@router.post("/transactions/{transaction_id}/reverse", response_model=TransactionOut,
             status_code=201)
def reverse_transaction(transaction_id: int, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """Audit-safe correction: creates a compensating record, keeps the original."""
    original = get_owned(db, Transaction, transaction_id, user.id)
    if original.reversed:
        raise HTTPException(status_code=409, detail="Already reversed")
    if original.reversal_of_id is not None:
        raise HTTPException(status_code=400, detail="Reversal records cannot be reversed")

    reversal = Transaction(
        user_id=user.id,
        type=original.type,
        amount_minor=original.amount_minor,
        currency=original.currency,
        occurred_on=date.today(),
        category="reversal",
        description=f"Reversal of transaction #{original.id}",
        from_account_id=original.to_account_id,
        to_account_id=original.from_account_id,
        reference=original.reference,
        reversal_of_id=original.id,
    )
    db.add(reversal)
    original.reversed = True
    db.commit()
    return reversal


@router.get("/transactions/summary/month", response_model=MonthSummary)
def month_summary(month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    try:
        year, mon = (month or date.today().strftime("%Y-%m")).split("-")
        start = date(int(year), int(mon), 1)
        end = date(int(year) + (int(mon) == 12), (int(mon) % 12) + 1, 1)
    except ValueError:
        raise HTTPException(status_code=422, detail="month must be YYYY-MM")
    from_ = select(func.coalesce(func.sum(Transaction.amount_minor), 0)).where(
        Transaction.user_id == user.id,
        Transaction.occurred_on >= start,
        Transaction.occurred_on < end,
    )
    income = db.scalar(from_.where(Transaction.type == "income")) or 0
    expense = db.scalar(from_.where(Transaction.type == "expense")) or 0
    transfers = db.scalar(from_.where(Transaction.type == "transfer")) or 0
    return MonthSummary(
        income_minor=income, expense_minor=expense, transfers_minor=transfers
    )
