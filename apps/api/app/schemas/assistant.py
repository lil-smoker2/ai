"""AI Assistant contracts.

Cards and proposals are intentionally lightly-typed (dict/list) because the
assistant assembles heterogeneous result cards. Figures inside cards always
come from saved records; unknown values stay null rather than fabricated.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelStatus(BaseModel):
    """The optional local model's load state, driven from the AI page.

    ``available`` reports whether a load could succeed at all (feature enabled,
    a *.gguf found, llama-cpp importable); ``error`` explains why not. Nothing
    is loaded until the user asks, so ``state`` starts as ``unloaded``.
    """

    enabled: bool
    available: bool
    state: Literal["unloaded", "loading", "ready", "failed"]
    model_file: str | None
    size_mb: float | None
    threads: int
    ctx: int
    error: str | None = None


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None
    # Optional product image to analyse this turn.
    asset_id: str | None = Field(default=None, max_length=36)


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    payload: dict
    status: str
    result: dict | None
    created_at: datetime
    resolved_at: datetime | None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    cards: list | None
    asset_id: str | None
    created_at: datetime
    # Attached only on assistant messages that propose a change.
    proposal: ProposalOut | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetail(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]


class SendResponse(BaseModel):
    conversation_id: int
    user_message: MessageOut
    assistant_message: MessageOut


class ConfirmResponse(BaseModel):
    proposal: ProposalOut
    assistant_message: MessageOut
