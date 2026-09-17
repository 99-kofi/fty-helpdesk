"""AI stub (spec §12-13): retrieval-only suggestions, human-in-the-loop by default."""
from sqlalchemy.orm import Session
from app.models.knowledge import KnowledgeArticle


def suggest_reply(db: Session, content: str) -> dict:
    words = [w for w in content.lower().split() if len(w) > 3][:6]
    hits = []
    if words:
        q = db.query(KnowledgeArticle)
        for w in words:
            hits = q.filter(KnowledgeArticle.body.ilike(f"%{w}%")).limit(3).all()
            if hits:
                break
    return {
        "intent": "general_question",
        "confidence": 0.5,
        "requires_human": True,
        "suggestions": [{"title": h.title, "body": h.body[:500]} for h in hits],
    }
