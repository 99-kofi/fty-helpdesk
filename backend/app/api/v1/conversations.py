import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.websocket import broadcast
from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_user, require_role
from app.models.conversation import Conversation, Message
from app.models.assignment import AssignmentHistory
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas import ConversationIn, ConversationOut, MessageIn, MessageOut
from app.services.assignment import record_history

PRIORITIES = {"low", "normal", "high", "urgent"}
STATUSES = {"new", "open", "assigned", "in_progress", "waiting_for_customer", "resolved", "closed", "reopened"}

log = logging.getLogger("fty.inbox")

router = APIRouter(tags=["conversations"], dependencies=[Depends(get_current_user)])


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(scope: str = "all", db: Session = Depends(get_db),
                       me: User = Depends(get_current_user)):
    """Admin sees everything; everyone else sees only assigned work."""
    q = db.query(Conversation)
    if me.role != "admin":
        scope = "mine"
    if scope == "mine":
        q = q.filter(Conversation.assigned_agent_id == me.id)
    elif scope == "unassigned":
        q = q.filter(Conversation.assigned_agent_id.is_(None))
    return q.order_by(Conversation.updated_at.desc()).limit(100).all()


def _ensure_access(conv: Conversation, me: User) -> None:
    if me.role == "admin":
        return
    if conv.assigned_agent_id != me.id:
        raise HTTPException(403, "Restricted: you can only access customers assigned to you")


@router.post("/conversations", response_model=ConversationOut,
              dependencies=[Depends(require_role("admin"))])
def create_conversation(data: ConversationIn, db: Session = Depends(get_db)):
    c = Conversation(**data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.get("/conversations/updates")
def updates(since: int = 0, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """New customer messages since a message id — powers inbox notifications."""
    q = db.query(Message).filter(Message.id > since, Message.sender_type == "customer")
    if me.role != "admin":
        from sqlalchemy import select
        mine_ids = select(Conversation.id).where(Conversation.assigned_agent_id == me.id)
        q = q.filter(Message.conversation_id.in_(mine_ids))
    msgs = q.order_by(Message.id).limit(50).all()
    latest = max([m.id for m in msgs], default=since)
    return {"latest": latest, "messages": [
        {"id": m.id, "conversation_id": m.conversation_id, "content": m.content[:160]} for m in msgs
    ]}


@router.get("/conversations/{cid}/messages", response_model=list[MessageOut])
def list_messages(cid: int, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    conv = db.get(Conversation, cid)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    _ensure_access(conv, me)
    return db.query(Message).filter_by(conversation_id=cid).order_by(Message.id).all()


async def _after_agent_message(conversation_id: int, text: str) -> None:
    """Best-effort: deliver the reply to the channel, then push a realtime event."""
    from app.channels.sending import deliver
    db = SessionLocal()
    try:
        conv = db.get(Conversation, conversation_id)
        if conv is None:
            return
        external_id = await deliver(db, conv, text)
        if external_id:
            latest = (
                db.query(Message)
                .filter_by(conversation_id=conversation_id, sender_type="agent")
                .order_by(Message.id.desc())
                .first()
            )
            if latest and not latest.external_message_id:
                latest.external_message_id = external_id
                db.commit()
        await broadcast({"type": "message", "conversation_id": conversation_id, "sender": "agent"})
    except Exception:
        log.exception("post-send hook failed")
    finally:
        db.close()


@router.post("/conversations/{cid}/messages", response_model=MessageOut)
def send_message(cid: int, data: MessageIn, background: BackgroundTasks, db: Session = Depends(get_db),
                 me: User = Depends(get_current_user)):
    conv = db.get(Conversation, cid)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    _ensure_access(conv, me)
    # Reopen closed on customer reply (spec §7)
    if data.sender_type == "customer" and conv.status == "closed":
        conv.status = "reopened"
    m = Message(conversation_id=cid, **data.model_dump())
    db.add(m)
    db.add(AuditLog(actor=data.sender_id or data.sender_type, action="message_sent", entity="conversation", entity_id=cid))
    db.commit()
    db.refresh(m)
    if data.sender_type in ("agent", "ai"):
        background.add_task(_after_agent_message, cid, data.content)
    return m


@router.patch("/conversations/{cid}/assign", dependencies=[Depends(require_role("admin"))])
def assign(cid: int, background: BackgroundTasks, agent_id: int | None = None,
           team: str | None = None, priority: str | None = None,
           reason: str | None = None, clear: bool = False,
           db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Manual assign/reassign (spec §3A, §9): worker + team + priority + reason, all audited."""
    conv = db.get(Conversation, cid)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    _ensure_access(conv, me)
    from_u, from_t = conv.assigned_agent_id, conv.assigned_team

    if clear:
        conv.assigned_agent_id = None
        record_history(db, conv, "unassigned", assigned_by=me.name,
                       from_user_id=from_u, to_user_id=None, reason=reason or "sent back to queue")
    else:
        if agent_id is not None:
            if not db.get(User, agent_id):
                raise HTTPException(404, "Agent not found")
            conv.assigned_agent_id = agent_id
        if team is not None:
            conv.assigned_team = team or None
        if priority is not None:
            if priority not in PRIORITIES:
                raise HTTPException(422, "Bad priority")
            if conv.priority != priority:
                record_history(db, conv, "priority_changed", assigned_by=me.name,
                               detail=f"{conv.priority} → {priority}", reason=reason)
                conv.priority = priority
        if conv.status in ("new", "open") and (conv.assigned_agent_id or conv.assigned_team):
            conv.status = "assigned"
        to_u = conv.assigned_agent_id
        if from_u is None and to_u is not None:
            action = "assigned"
        elif from_u != to_u or (from_t or None) != (conv.assigned_team or None):
            action = "reassigned"  # new worker or new team — history preserved (§9)
        else:
            action = "assigned"
        record_history(db, conv, action, assigned_by=me.name,
                       from_user_id=from_u, to_user_id=to_u,
                       from_team=from_t, to_team=conv.assigned_team, reason=reason)
    db.add(AuditLog(actor=me.name, action="assignment", entity="conversation", entity_id=cid,
                    detail=f"agent={conv.assigned_agent_id} team={conv.assigned_team}"))
    db.commit()
    background.add_task(broadcast, {"type": "assignment", "conversation_id": cid})
    return {"ok": True}


@router.patch("/conversations/{cid}/status")
def set_status(cid: int, status: str, db: Session = Depends(get_db),
               me: User = Depends(get_current_user)):
    conv = db.get(Conversation, cid)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    _ensure_access(conv, me)
    if status not in STATUSES:
        raise HTTPException(422, "Bad status")
    if conv.status != status:
        old = conv.status
        conv.status = status
        record_history(db, conv, "status_changed", assigned_by=me.name, detail=f"{old} → {status}")
        db.commit()
    return {"ok": True, "status": conv.status}


@router.get("/conversations/{cid}/history")
def history(cid: int, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    conv = db.get(Conversation, cid)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    _ensure_access(conv, me)
    rows = (db.query(AssignmentHistory).filter_by(conversation_id=cid)
            .order_by(AssignmentHistory.id).all())
    return [{"id": h.id, "action": h.action, "from_user_id": h.from_user_id,
             "to_user_id": h.to_user_id, "from_team": h.from_team, "to_team": h.to_team,
             "detail": h.detail, "reason": h.reason, "assigned_by": h.assigned_by,
             "created_at": h.created_at.isoformat() if h.created_at else None} for h in rows]
