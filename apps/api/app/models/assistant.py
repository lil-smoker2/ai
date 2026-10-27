"""AI assistant persistence: conversations, messages and confirmation-gated
proposed actions.

The assistant is deterministic and offline: it reasons over saved records via
validated read-tools and never invents data. Any change it wants to make is
stored as a *proposed action* that stays inert until the user explicitly
confirms it (spec 4.11 / MVP rule: AI-generated changes require confirmation).
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow

MESSAGE_ROLES = ("user", "assistant")
PROPOSAL_STATUSES = ("pending", "confirmed", "dismissed")


class Conversation(Base):
    __tablename__ = "assistant_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(160), default="New chat")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class Message(Base):
    __tablename__ = "assistant_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("assistant_conversations.id"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(Enum(*MESSAGE_ROLES, name="chat_role"))
    content: Mapped[str] = mapped_column(Text, default="")
    # Structured result cards the frontend renders; never fabricated figures.
    cards: Mapped[list | None] = mapped_column(JSON, default=None)
    # Asset id when this turn analysed a product image (nullable).
    asset_id: Mapped[str | None] = mapped_column(String(36), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProposedAction(Base):
    """A change the assistant wants to make. Inert until confirmed."""

    __tablename__ = "assistant_proposed_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("assistant_conversations.id"), index=True
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("assistant_messages.id"), default=None
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # "create_tasks_from_goals" | "add_inventory_item"
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(160), default="")
    # Validated, self-contained parameters used only if the user confirms.
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(
        Enum(*PROPOSAL_STATUSES, name="proposal_status"), default="pending"
    )
    # Populated after confirmation with the ids actually written.
    result: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
