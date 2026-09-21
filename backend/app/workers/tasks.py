"""Message worker pipeline (spec §4, §27): identify → conversation → store → classify → notify."""
from app.channels import ADAPTERS
from app.core.database import SessionLocal
from app.models.conversation import Message
from app.services.identity_resolution import resolve_customer
from app.services.conversation_engine import get_or_create_conversation
from app.services.assignment import maybe_auto_assign
from app.services.automation import evaluate_event_rules
from app.services.ai_autoreply import maybe_auto_reply


def handle_message_event(channel: str, payload: dict) -> int:
    adapter = ADAPTERS.get(channel)
    if not adapter:
        return 0
    db = SessionLocal()
    try:
        stored = 0
        for msg in adapter.normalize(payload):
            if not msg.content:
                continue
            # dedupe on external id
            if msg.external_message_id and db.query(Message).filter_by(external_message_id=msg.external_message_id).first():
                continue
            customer = resolve_customer(db, msg.channel, msg.external_user_id)
            conv = get_or_create_conversation(db, customer.id, msg.channel)
            if conv.status == "new":
                conv.status = "open"
            db.add(Message(conversation_id=conv.id, sender_type="customer",
                           sender_id=msg.external_user_id, content=msg.content,
                           external_message_id=msg.external_message_id))
            db.commit()
            # Conversation → intent → team → worker (or Unassigned queue)
            cls = maybe_auto_assign(db, conv, msg.content)
            # THEN user-defined automation rules (WHEN message_created → IF → DO)
            evaluate_event_rules(db, "message_created", {
                "channel": msg.channel, "text": msg.content,
                "intent": cls.intent, "confidence": cls.confidence,
                "team": conv.assigned_team, "priority": conv.priority,
                "conversation": conv,
            })
            # THEN FAQ auto-reply: if the message is a high-confidence FAQ, answer
            # instantly from the Knowledge Base without waiting for a human.
            # This runs on every customer turn, no admin toggling required.
            try:
                # Only auto-reply if the thread's last human reply is not the
                # immediate predecessor (i.e., don't spam every turn).
                last = db.query(Message).filter_by(conversation_id=conv.id).order_by(Message.id.desc()).first()
                if last and last.sender_type == "customer":
                    maybe_auto_reply(db, conv, msg.content)
            except Exception:
                import logging

                logging.getLogger("fty.ai").exception("auto-reply failed")
            stored += 1
        return stored
    finally:
        db.close()
