"""AI stub (spec §12-13): retrieval-only suggestions, human-in-the-loop by default."""
import re
from sqlalchemy.orm import Session
from app.models.knowledge import KnowledgeArticle


# High-confidence FAQ intents that the AI is allowed to answer on first contact,
# without waiting for an admin to go unavailable. Low-risk, knowledge-base-backed.
FAQ_RULES: list[tuple[str, float, tuple[str, ...]]] = [
    ("shipping_question", 0.92, ("ship", "shipping", "delivery", "deliver", "track", "tracking", "courier", "dhl", "where is my order", "when will it arrive")),
    ("return_policy", 0.92, ("return policy", "how to return", "can i return", "refund policy", "exchange policy")),
    ("return_request", 0.88, ("return", "refund", "exchange", "wrong size", "damaged", "defective", "not what i ordered")),
    ("payment_question", 0.88, ("payment", "pay", "momo", "mobile money", "card", "visa", "mastercard", "cash on delivery")),
    ("sizing_question", 0.88, ("size", "sizes", "sizing", "fit", "how does it fit", "true to size", "oversized")),
    ("restock_question", 0.88, ("restock", "restocked", "sold out", "out of stock", "when will it be back")),
    ("store_info", 0.90, ("store", "location", "where are you", "pop up", "pop-up", "hours")),
]

NON_FAQ = ("complaint", "angry", "terrible", "awful", "worst", "fraud", "scam", "stolen", "charged twice", "lawsuit")


def classify_faq(content: str) -> tuple[str, float]:
    text = content.lower()
    if any(k in text for k in NON_FAQ):
        return "complaint", 0.35
    for intent, conf, keywords in FAQ_RULES:
        if any(k in text for k in keywords):
            # Short, question-like messages score higher.
            if len(text) < 120 and "?" in content:
                conf = min(0.96, conf + 0.04)
            # Penalize very long or multi-intent messages.
            if len(text) > 280:
                conf -= 0.08
            return intent, round(conf, 2)
    return "general_question", 0.45


def _keywords(text: str) -> list[str]:
    # Content words, 4+ chars, deduped in order.
    words = re.findall(r"[a-z]{4,}", text.lower())
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
        if len(out) >= 6:
            break
    return out


def suggest_reply(db: Session, content: str) -> dict:
    intent, confidence = classify_faq(content)
    hits: list[KnowledgeArticle] = []
    for w in _keywords(content):
        candidates = db.query(KnowledgeArticle).filter(
            (KnowledgeArticle.title.ilike(f"%{w}%")) | (KnowledgeArticle.body.ilike(f"%{w}%"))
        ).limit(3).all()
        if candidates:
            hits = candidates
            break
    # If intent is FAQ-like but keyword search missed, fall back to category.
    if not hits and confidence >= 0.85:
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
            hits = db.query(KnowledgeArticle).filter(KnowledgeArticle.category == cat).limit(2).all()

    is_faq = confidence >= 0.88 and intent in {r[0] for r in FAQ_RULES}
    return {
        "intent": intent,
        "confidence": confidence,
        "requires_human": not is_faq,
        "auto_reply_eligible": is_faq,
        "suggestions": [{"title": h.title, "body": h.body[:600]} for h in hits],
    }
