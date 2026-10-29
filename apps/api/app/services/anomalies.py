"""Unusual expenses, measured against the user's own spending.

Nothing here knows what "too much" is for anyone else. A cost is only called
unusual when the same category has been spent on often enough to have a real
middle: the reference is that category's own median, and the spread is its MAD
(the median of how far each amount sits from that median). The classical
threshold of a modified z-score of 3.5 is used unchanged; below it, nothing is
reported.

The honesty rules that shape when the answer is silent:

* A category with fewer than MIN_CATEGORY_EXPENSES recorded expenses has no
  dependable middle, so none of its amounts are ever flagged - not even huge
  ones. An outlier test needs a population, not a pair.
* Only expenses count. Income, transfers, reversals and the compensating
  records they create are not spending and cannot be unusual spending.
* Every figure returned is an integer of minor units taken straight from a
  saved transaction, alongside the median it was judged against - the reader
  can check the comparison rather than having to trust a verdict.
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import Transaction
from app.models.user import User

# How far back "usual" is measured. Spending habits drift; a comparison that
# reaches years back would call last year's normal this year's anomaly.
LOOKBACK_DAYS = 90

# A category needs this many recorded expenses before its median means
# anything, and the same count keeps the MAD from collapsing to zero on a
# couple of identical amounts.
MIN_CATEGORY_EXPENSES = 5

# Classical modified z-score cutoff for a MAD-based outlier test.
Z_SCORE_THRESHOLD = 3.5


def _flagged(amounts: list[int], amount: int) -> float | None:
    """Modified z-score of one amount against its category, or None.

    A zero MAD means every recorded amount is effectively the same; a score is
    only meaningful against real spread, and an identical amount is not an
    outlier against its own copy.
    """
    med = median(amounts)
    deviations = [abs(a - med) for a in amounts]
    mad = median(deviations)
    if mad <= 0:
        return None
    return 0.6745 * (amount - med) / mad


def find_expense_anomalies(db: Session, user: User,
                           today: date | None = None) -> dict:
    """Expenses that stand out against their own category's recorded middle."""
    today = today or date.today()
    cutoff = today - timedelta(days=LOOKBACK_DAYS)

    rows = db.scalars(
        select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.type == "expense",
            Transaction.reversed.is_(False),
            Transaction.reversal_of_id.is_(None),
            Transaction.occurred_on >= cutoff,
            Transaction.occurred_on <= today,
        )
    ).all()

    # One display label (the first spelling seen) per lower-cased category.
    groups: dict[str, dict] = {}
    for t in sorted(rows, key=lambda t: (t.occurred_on, t.id)):
        label = (t.category or "").strip() or "Uncategorized"
        key = label.lower()
        group = groups.setdefault(key, {"label": label, "amounts": []})
        group["amounts"].append(t.amount_minor)
        group.setdefault("txns", []).append(t)

    anomalies: list[dict] = []
    for group in groups.values():
        if len(group["amounts"]) < MIN_CATEGORY_EXPENSES:
            continue  # too few to know what usual is for this category
        amounts = group["amounts"]
        for t, amount in zip(group["txns"], amounts):
            score = _flagged(amounts, amount)
            if score is None or score <= Z_SCORE_THRESHOLD:
                continue
            anomalies.append({
                "transaction_id": t.id,
                "description": t.description,
                "category": group["label"],
                "amount_minor": amount,
                "currency": t.currency,
                "occurred_on": t.occurred_on,
                "category_median_minor": int(median(amounts)),
                "deviation_score": round(score, 2),
            })

    anomalies.sort(key=lambda a: -a["deviation_score"])
    return {
        "generated_on": today,
        "window_days": LOOKBACK_DAYS,
        "min_category_expenses": MIN_CATEGORY_EXPENSES,
        "anomalies": anomalies,
    }
