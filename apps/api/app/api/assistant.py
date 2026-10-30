"""AI Assistant API.

Turns are grounded in saved data via the deterministic service. The assistant
never writes on its own: it can only return *proposals*, and the endpoints
below persist those proposals as inert rows until the user explicitly confirms
(or dismisses) them. Confirmation is the only path that writes records, and it
reuses the same validated model logic the normal modules use.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned
from app.core.database import get_db
from app.models.assistant import Conversation, Message, ProposedAction
from app.models.inventory import InventoryCategory, InventoryItem
from app.models.tasks import Task
from app.models.user import User, utcnow
from app.schemas.assistant import (
    AssistantRequest,
    ConfirmResponse,
    ConversationDetail,
    ConversationOut,
    MessageOut,
    ModelStatus,
    ProposalOut,
    SendResponse,
)
from app.services import assistant as assistant_service
from app.services import llm

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

SUGGESTED_PROMPTS = [
    "What am I missing in my wardrobe?",
    "Help me budget for next semester.",
    "Which goals should I prioritize?",
    "What fees and obligations are due soon?",
    "Turn my goals into weekly tasks.",
    "How do I add an expense?",
    "How do I track my course fees?",
]


@router.get("/suggestions", response_model=list[str])
def suggestions():
    return SUGGESTED_PROMPTS


# --- Optional local model -------------------------------------------------

# The GGUF is deliberately never loaded at startup: the AI page asks for these
# endpoints. Loading happens in a background thread, so the caller polls
# GET /model until the state settles at "ready" or "failed".

@router.get("/model", response_model=ModelStatus)
def model_status(user: User = Depends(get_current_user)):
    return llm.status()


@router.post("/model/load", response_model=ModelStatus)
def model_load(user: User = Depends(get_current_user)):
    return llm.load_model()


@router.post("/model/unload", response_model=ModelStatus)
def model_unload(user: User = Depends(get_current_user)):
    return llm.unload_model()


def _proposal_out(action: ProposedAction) -> ProposalOut:
    return ProposalOut.model_validate(action)


def _message_out(db: Session, msg: Message) -> MessageOut:
    action = db.scalars(
        select(ProposedAction).where(ProposedAction.message_id == msg.id)
    ).first()
    out = MessageOut.model_validate(msg)
    out.proposal = _proposal_out(action) if action else None
    return out


@router.post("/messages", response_model=SendResponse)
def send(
    body: AssistantRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.conversation_id is None:
        title = body.message.strip()[:60] or "New chat"
        convo = Conversation(user_id=user.id, title=title)
        db.add(convo)
        db.flush()
    else:
        convo = get_owned(db, Conversation, body.conversation_id, user.id)

    user_msg = Message(
        conversation_id=convo.id, user_id=user.id, role="user",
        content=body.message, asset_id=body.asset_id,
    )
    db.add(user_msg)
    db.flush()

    reply = assistant_service.respond(db, user, body.message, body.asset_id)

    assistant_msg = Message(
        conversation_id=convo.id, user_id=user.id, role="assistant",
        content=reply["content"], cards=reply.get("cards") or None,
        asset_id=body.asset_id,
    )
    db.add(assistant_msg)
    db.flush()

    proposal = reply.get("proposal")
    if proposal:
        db.add(ProposedAction(
            conversation_id=convo.id, message_id=assistant_msg.id, user_id=user.id,
            kind=proposal["kind"], title=proposal["title"],
            payload=proposal["payload"], status="pending",
        ))

    convo.updated_at = utcnow()
    db.commit()
    return SendResponse(
        conversation_id=convo.id,
        user_message=_message_out(db, user_msg),
        assistant_message=_message_out(db, assistant_msg),
    )


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    convos = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.deleted_at.is_(None))
        .order_by(Conversation.updated_at.desc())
    ).all()
    out = []
    for c in convos:
        count = db.scalar(
            select(func.count(Message.id)).where(Message.conversation_id == c.id)
        ) or 0
        item = ConversationOut.model_validate(c)
        item.message_count = count
        out.append(item)
    return out


@router.get("/web-search")
def web_search_endpoint(q: str, user: User = Depends(get_current_user)):
    from app.services import llm
    return llm.web_search(q)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    convo = get_owned(db, Conversation, conversation_id, user.id)
    msgs = db.scalars(
        select(Message)
        .where(Message.conversation_id == convo.id)
        .order_by(Message.id)
    ).all()
    count = db.scalar(
        select(func.count(Message.id)).where(Message.conversation_id == convo.id)
    ) or 0
    convo_out = ConversationOut.model_validate(convo)
    convo_out.message_count = count
    return ConversationDetail(
        conversation=convo_out, messages=[_message_out(db, m) for m in msgs]
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    convo = get_owned(db, Conversation, conversation_id, user.id)
    convo.deleted_at = utcnow()
    db.commit()


def _get_or_create_category(db: Session, user: User, name: str) -> InventoryCategory:
    existing = db.scalars(
        select(InventoryCategory).where(
            InventoryCategory.user_id == user.id,
            func.lower(InventoryCategory.name) == name.lower(),
        )
    ).first()
    if existing:
        return existing
    cat = InventoryCategory(user_id=user.id, name=name)
    db.add(cat)
    db.flush()
    return cat


@router.post("/proposals/{proposal_id}/confirm", response_model=ConfirmResponse)
def confirm(
    proposal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    action = get_owned(db, ProposedAction, proposal_id, user.id)
    if action.status != "pending":
        raise HTTPException(status_code=409, detail=f"Already {action.status}")

    convo = get_owned(db, Conversation, action.conversation_id, user.id)
    payload = action.payload or {}

    if action.kind == "create_tasks_from_goals":
        created = []
        for t in payload.get("tasks", []):
            task = Task(
                user_id=user.id,
                title=str(t.get("title"))[:120],
                due_on=date.fromisoformat(t["due_on"]) if t.get("due_on") else None,
                priority=t.get("priority") or "medium",
                goal_id=t.get("goal_id"),
                status="pending",  # approved by the user via confirmation
            )
            db.add(task)
            db.flush()
            created.append(task.id)
        action.result = {"task_ids": created}
        summary = f"Done — I created {len(created)} task(s) from your goals."
    elif action.kind == "add_inventory_item":
        category = _get_or_create_category(
            db, user, str(payload.get("category") or "General")
        )
        item = InventoryItem(
            user_id=user.id,
            category_id=category.id,
            name=str(payload.get("name") or "Item")[:120],
            quantity_owned=int(payload.get("quantity") or 0),
            # Price is never inferred from an image; it stays null until entered.
            estimated_unit_cost_minor=payload.get("estimated_unit_cost_minor"),
            price_verified=False,
            image_asset_id=payload.get("image_asset_id"),
        )
        db.add(item)
        db.flush()
        action.result = {"item_id": item.id}
        summary = (
            f"Added “{item.name}” to inventory with no price. Enter a price and "
            "quantity if you'd like me to track a shortfall for it."
        )
    else:
        raise HTTPException(status_code=400, detail="Unknown proposal kind")

    action.status = "confirmed"
    action.resolved_at = utcnow()

    summary_msg = Message(
        conversation_id=convo.id, user_id=user.id, role="assistant",
        content=summary, cards=None,
    )
    db.add(summary_msg)
    convo.updated_at = utcnow()
    db.commit()
    return ConfirmResponse(
        proposal=_proposal_out(action), assistant_message=_message_out(db, summary_msg)
    )


@router.post("/proposals/{proposal_id}/dismiss", response_model=ProposalOut)
def dismiss(
    proposal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    action = get_owned(db, ProposedAction, proposal_id, user.id)
    if action.status != "pending":
        raise HTTPException(status_code=409, detail=f"Already {action.status}")
    action.status = "dismissed"
    action.resolved_at = utcnow()
    db.commit()
    return _proposal_out(action)
