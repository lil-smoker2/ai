"""Account operations contracts: the factory reset.

The confirmation phrase is required in the body, not assumed from the HTTP
verb, because the desktop app signs you in automatically - there is no
password to re-enter, so the typed word is the only deliberate step.
"""
from pydantic import BaseModel

CONFIRM_PHRASE = "RESET"


class ResetRequest(BaseModel):
    confirm: str

    def confirmed(self) -> bool:
        return self.confirm.strip().upper() == CONFIRM_PHRASE


class ResetResult(BaseModel):
    deleted: dict[str, int]
    deleted_total: int
    kept: list[str]
    reseeded: list[str]
    note: str
