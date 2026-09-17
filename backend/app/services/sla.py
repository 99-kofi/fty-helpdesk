"""SLA watchdog (Phase 3): unanswered customers and stale tickets get escalated.

- Conversation: latest message is customer-sent and older than
  sla_first_response_minutes → priority urgent + on-duty manager + history.
- Ticket: open/in_progress older than sla_resolution_hours → same treatment.

Idempotent: never escalates twice for the same waiting message / ticket state.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.assignment import AssignmentHistory
from app.models.conversation import Conversation, Message
from app.models.ticket import Ticket, TicketEvent
from app.services.assignment import OPEN_STATES, find_candidate, record_history

log = logging.getLogger("fty.sla")


def _now():
    return datetime.now(timezone.utc)


def _age_minutes(dt) -> float:
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (_now() - dt).total_seconds() / 60.0


def _already_escalated(db: Session, conv_id: int, since) -> bool:
    q = db.query(AssignmentHistory).filter_by(conversation_id=conv_id, action="escalated")
    if since is not None:
        naive = since.replace(tzinfo=None) if getattr(since, "tzinfo", None) else since
        q = q.filter(AssignmentHistory.created_at > naive)
    return q.count() > 0


def check_conversations(db: Session) -> int:
    n = 0
    convs = db.query(Conversation).filter(Conversation.status.in_(OPEN_STATES)).all()
    for conv in convs:
        latest_customer = (
            db.query(Message).filter_by(conversation_id=conv.id, sender_type="customer")
            .order_by(Message.id.desc()).first()
        )
        if not latest_customer:
            continue
        latest_any = (
            db.query(Message).filter_by(conversation_id=conv.id)
            .order_by(Message.id.desc()).first()
        )
        if latest_any.sender_type != "customer":
            continue  # already answered
        if _age_minutes(latest_customer.created_at) < settings.sla_first_response_minutes:
            continue
        if _already_escalated(db, conv.id, latest_customer.created_at):
            continue
        mgr = find_candidate(db, conv.assigned_team, urgent_bypass=True)
        if conv.priority != "urgent":
            record_history(db, conv, "priority_changed", assigned_by="sla-watch",
                           detail=f"{conv.priority} → urgent",
                           reason=f"no reply for {settings.sla_first_response_minutes}m")
            conv.priority = "urgent"
        if mgr and conv.assigned_agent_id != mgr.id:
            record_history(db, conv, "escalated", assigned_by="sla-watch",
                           to_user_id=mgr.id, reason="SLA breach → on-duty manager")
            conv.assigned_agent_id = mgr.id
            if conv.status in ("new", "open"):
                conv.status = "assigned"
        else:
            record_history(db, conv, "escalated", assigned_by="sla-watch",
                           reason="SLA breach (no manager available)")
        n += 1
    if n:
        db.commit()
        log.info("sla: escalated %d conversations", n)
    return n


def check_tickets(db: Session) -> int:
    n = 0
    cutoff_min = settings.sla_resolution_hours * 60
    tickets = db.query(Ticket).filter(Ticket.status.in_(("open", "in_progress"))).all()
    for t in tickets:
        if _age_minutes(t.created_at) < cutoff_min:
            continue
        if db.query(TicketEvent).filter_by(ticket_id=t.id, action="escalated").first():
            continue
        mgr = find_candidate(db, None, urgent_bypass=True)
        if t.priority != "urgent":
            t.priority = "urgent"
        if mgr:
            t.assigned_to = mgr.id
        db.add(TicketEvent(ticket_id=t.id, actor="sla-watch", action="escalated",
                           detail=f"unresolved for {settings.sla_resolution_hours}h"))
        n += 1
    if n:
        db.commit()
        log.info("sla: escalated %d tickets", n)
    return n


def run_sla_check(db: Session) -> dict:
    return {
        "conversations_escalated": check_conversations(db),
        "tickets_escalated": check_tickets(db),
    }
