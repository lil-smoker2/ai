from pydantic import BaseModel


class DashboardSummary(BaseModel):
    # None means "not initialized/unknown", deliberately not zero.
    total_available_minor: int | None
    income_this_month_minor: int
    expenses_this_month_minor: int
    savings_this_month_minor: int
    active_goals: int
    outstanding_goal_amount_minor: int
    distinct_inventory_items: int
    items_below_target: int
    # Null when some below-target items lack prices (never faked as zero cost).
    estimated_shortage_cost_minor: int | None
    price_needed_items: int
    # Saved value of the things you own (see /api/networth). Null when some
    # owned items have no price, or before anything has been recorded.
    net_worth_minor: int | None
