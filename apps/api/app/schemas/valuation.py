"""Net worth contracts.

Everything here is derived from inventory records; no figure is typed by the
user. Unknown values stay null instead of being flattened to zero, so a total
is only presented as a total when nothing had to be left out.
"""
from datetime import date, datetime

from pydantic import BaseModel


class ValuationLine(BaseModel):
    item_id: int
    name: str
    category_name: str | None
    # Folder label used to find the item's picture ("clothing/trousers").
    category_slug: str | None
    quantity_owned: int
    unit: str | None
    target_quantity: int | None
    # How many more are needed to reach the target (0 when no target set).
    needed_quantity: int
    unit_cost_minor: int | None
    price_verified: bool
    # quantity_owned * unit cost; null only when the item is owned but unpriced.
    value_minor: int | None
    # Cost of the shortfall; null when a shortfall has no price yet.
    to_target_minor: int | None
    price_needed: bool
    image_asset_id: str | None


class NetWorthSaved(BaseModel):
    on_date: date
    # Null when part of the worth is unpriced - recorded as "not known yet".
    net_worth_minor: int | None
    priced_value_minor: int
    valued_items: int
    unpriced_items: int
    complete: bool
    updated_at: datetime


class NetWorthTrend(BaseModel):
    """Direction read off the saved snapshots - absent when they are too few.

    Unknown days are reported as gaps and excluded from the arithmetic; no
    figure is ever interpolated to complete the line."""

    from_date: date
    to_date: date
    known_days: int
    gap_days: int
    slope_minor_per_day: int
    change_minor: int
    recent_average_minor: int
    # "building" | "steady" | "declining" - only once the slope clears the band.
    direction: str


class Valuation(BaseModel):
    currency: str
    lines: list[ValuationLine]

    items: int
    units_owned: int
    units_needed: int

    # Value of what is owned. Null while any owned item lacks a price.
    net_worth_minor: int | None
    # Sum over the priced items only, so the page can still say "at least".
    priced_value_minor: int
    valued_items: int
    unpriced_items: int

    # Money still required to reach every target (same null rule).
    to_target_minor: int | None
    # Owned value + cost to target: the money to have everything you want.
    replacement_total_minor: int | None

    saved: NetWorthSaved | None
    history: list[NetWorthSaved]
    # None until at least three complete days exist to read a direction from.
    trend: NetWorthTrend | None
    note: str
