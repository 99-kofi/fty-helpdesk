"""Conversation engine (spec §7): find-or-create open conversation, handle reopen."""
from sqlalchemy.orm import Session
from app.models.conversation import Conversation

OPEN_STATES = {"new", "open", "assigned", "in_progress", "waiting_for_customer", "reopened"}


def get_or_create_conversation(db: Session, customer_id: int, channel: str) -> Conversation:
    conv = (
        db.query(Conversation)
        .filter(Conversation.customer_id == customer_id, Conversation.status.in_(OPEN_STATES))
        .order_by(Conversation.updated_at.desc())
        .first()
    )
    if conv:
        return conv
    conv = Conversation(customer_id=customer_id, channel=channel, status="new")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv
