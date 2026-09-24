"""AI auto-responder (Phase 3): answer FAQs immediately without admin action.

Eligible intents are the high-confidence, low-risk ones in ai_stub.FAQ_RULES
(shipping, returns, payments, sizing, restock, store info). The reply is always
grounded in the Knowledge Base article - never hallucinated - and is marked as
sender_type="ai" with an audit note, so a human can follow up.

Gating:
  - Global toggle: settings.ai_auto_reply_enabled (bool, default True)
  - Scope: settings.ai_auto_reply_scope = "faq" (only FAQ_RULES) or "all"
  - Threshold: settings.ai_auto_reply_threshold (default 0.88)
  - Channel allowlist: settings.ai_auto_reply_channels (comma-separated, empty = all)
"""
import logging
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.conversation import Conversation, Message
from app.models.knowledge import KnowledgeArticle
from app.services.ai_stub import classify_faq

log = logging.getLogger("fty.ai")


def _channel_allowed(channel: str) -> bool:
    allow = [c.strip() for c in (settings.ai_auto_reply_channels or "").split(",") if c.strip()]
    return not allow or channel in allow


def _pick_article(db: Session, content: str, intent: str) -> KnowledgeArticle | None:
    from app.services.knowledge_seed import ensure_examples

    ensure_examples(db)
    text = content.lower()
    # Direct keyword hit first.
    q = db.query(KnowledgeArticle)
    for w in [w for w in text.split() if len(w) >= 4][:6]:
        hit = q.filter(
            (KnowledgeArticle.title.ilike(f"%{w}%")) | (KnowledgeArticle.body.ilike(f"%{w}%"))
        ).first()
        if hit:
            return hit
    # Fallback to the intent's category.
    cat_map = {
        "shipping_question": "Shipping",
        "return_policy": "Returns",
        "return_request": "Returns",
        "payment_question": "Payments",
        "sizing_question": "Products",
        "restock_question": "Products",
        "store_info": "General",
    }
    cat = cat_map.get(intent)
    if cat:
        return db.query(KnowledgeArticle).filter(KnowledgeArticle.category == cat).first()
    return None


def maybe_auto_reply(db: Session, conv: Conversation, content: str) -> Message | None:
    if not settings.ai_auto_reply_enabled:
        return None
    if not _channel_allowed(conv.channel):
        return None
    intent, confidence = classify_faq(content)
    if confidence < settings.ai_auto_reply_threshold:
        return None
    if settings.ai_auto_reply_scope == "faq":
        from app.services.ai_stub import FAQ_RULES

        if intent not in {r[0] for r in FAQ_RULES}:
            return None
    # Never auto-reply to an already-human-handled thread in this turn;
    # the caller ensures this is the first customer message since last agent reply.
    article = _pick_article(db, content, intent)
    if not article:
        return None
    # Prefer a KB-grounded LLM that has LEARNED from the full KB; fall back to article verbatim.
    body = article.body.strip()
    grounded = None
    try:
        from app.services.ai_llm import grounded_answer, _retrieve_kb_articles

        # Let the LLM learn from the most relevant KB articles for this message
        learned_articles = _retrieve_kb_articles(db, content, limit=3)
        # Ensure the primary article is included
        if not any(a['title'] == article.title for a in learned_articles):
            learned_articles = [{"title": article.title, "body": article.body, "category": article.category}] + learned_articles[:2]
        grounded = grounded_answer(content, learned_articles, db=db)
    except Exception:
        grounded = None
    if grounded:
        reply = grounded
        # Ensure attribution
        if "FTY Knowledge Base" not in reply and "FTY HelpDesk" not in reply:
            reply += "\n\n— Answered from FTY Knowledge Base."
    else:
        reply = body[:900]
        if len(body) > 900:
            reply += "…"
        reply += "\n\n— Answered instantly from FTY Knowledge Base. An agent will follow up if you need more help."
    msg = Message(conversation_id=conv.id, sender_type="ai", sender_id="fty-ai", content=reply)
    db.add(msg)
    # Keep the conversation open but mark that AI already responded; human can still claim it.
    if conv.status in ("new", "open"):
        conv.status = "open"
    db.commit()
    db.refresh(msg)
    log.info("ai auto-replied conversation %s intent=%s conf=%.2f article=%s", conv.id, intent, confidence, article.title)
    return msg
