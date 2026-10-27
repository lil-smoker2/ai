from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

GOAL_TYPES = ("money", "quantity", "obligation", "custom")
GOAL_PRIORITIES = ("low", "medium", "high", "critical")


class GoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(pattern=f"^({'|'.join(GOAL_TYPES)})$")
    target_amount_minor: int | None = Field(default=None, gt=0)
    target_quantity: int | None = Field(default=None, gt=0)
    current_quantity: int | None = Field(default=None, ge=0)
    estimated_unit_cost_minor: int | None = Field(default=None, ge=0)
    deadline: date | None = None
    priority: str = Field(default="medium", pattern=f"^({'|'.join(GOAL_PRIORITIES)})$")
    inventory_item_id: int | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def check_target(self) -> "GoalCreate":
        if self.type == "money" and self.target_amount_minor is None:
            raise ValueError("money goals require target_amount_minor")
        if self.type == "quantity" and self.target_quantity is None:
            raise ValueError("quantity goals require target_quantity")
        return self


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    status: str
    target_amount_minor: int | None
    target_quantity: int | None
    current_quantity: int | None
    estimated_unit_cost_minor: int | None
    deadline: date | None
    priority: str
    inventory_item_id: int | None
    notes: str | None
    created_at: datetime
    completed_at: datetime | None
    # Calculated from saved contributions/records only.
    amount_saved_minor: int = 0
    remaining_amount_minor: int | None = None
    remaining_quantity: int | None = None
    estimated_remaining_cost_minor: int | None = None
    required_monthly_saving_minor: int | None = None
    # "ok" | "no_deadline" | "deadline_passed" - never divide by zero.
    deadline_state: str = "no_deadline"


class ContributionCreate(BaseModel):
    amount_minor: int = Field(gt=0)
    occurred_on: date | None = None
    account_id: int | None = None
    transaction_id: int | None = None
    note: str | None = Field(default=None, max_length=255)


class ContributionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    goal_id: int
    amount_minor: int
    occurred_on: date
    account_id: int | None
    transaction_id: int | None
    note: str | None
