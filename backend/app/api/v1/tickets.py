from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.conversation import Conversation
from app.models.ticket import Ticket, TicketEvent
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas import TicketIn, TicketOut

router = APIRouter(prefix="/tickets", tags=["tickets"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[TicketOut])
def list_tickets(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    q = db.query(Ticket)
    if me.role != "admin":
        # Own tickets + tickets on own assigned customers.
        q = (q.outerjoin(Conversation, Conversation.id == Ticket.conversation_id)
             .filter(or_(Ticket.assigned_to == me.id,
                         Conversation.assigned_agent_id == me.id)))
    return q.order_by(Ticket.id.desc()).limit(100).all()


@router.post("", response_model=TicketOut)
def create_ticket(data: TicketIn, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    from app.models.conversation import Conversation
    from app.services.automation import evaluate_event_rules
    if me.role != "admin":
        conv = db.get(Conversation, data.conversation_id)
        if not conv or conv.assigned_agent_id != me.id:
            raise HTTPException(403, "Restricted: you can only file tickets on assigned customers")
    t = Ticket(**data.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    evaluate_event_rules(db, "ticket_created", {
        "text": t.category or "", "priority": t.priority, "ticket": t,
    })
    db.refresh(t)
    return t


@router.patch("/{tid}")
def update_ticket(tid: int, status: str | None = None, assigned_to: int | None = None,
                    db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    t = db.get(Ticket, tid)
    if not t:
        raise HTTPException(404, "Ticket not found")
    if me.role != "admin":
        conv = db.get(Conversation, t.conversation_id)
        mine = t.assigned_to == me.id or (conv is not None and conv.assigned_agent_id == me.id)
        if not mine:
            raise HTTPException(403, "Restricted: you can only access tickets assigned to you")
        if assigned_to is not None and assigned_to != t.assigned_to:
            raise HTTPException(403, "Restricted: only the admin reassigns tickets")
    if status:
        old = t.status
        t.status = status
        db.add(TicketEvent(ticket_id=tid, actor="api", action=f"{old}->{status}"))
        if status in ("resolved", "closed"):
            t.resolved_at = datetime.now(timezone.utc)
    if assigned_to is not None:
        t.assigned_to = assigned_to
    db.add(AuditLog(actor="api", action="ticket_updated", entity="ticket", entity_id=tid, detail=status))
    db.commit()
    return {"ok": True}
