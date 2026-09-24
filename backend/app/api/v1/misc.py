from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.user import User
from app.schemas import UserOut

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/agents", response_model=list[UserOut], tags=["teams"])
def list_agents(db: Session = Depends(get_db)):
    return db.query(User).limit(100).all()


@router.get("/analytics/summary", tags=["analytics"],
              dependencies=[Depends(require_role("admin"))])
def analytics_summary(db: Session = Depends(get_db)):
    from app.models.conversation import Conversation, Message
    from app.models.ticket import Ticket
    return {
        "conversations": db.query(Conversation).count(),
        "messages": db.query(Message).count(),
        "tickets": db.query(Ticket).count(),
    }


@router.post("/ai/suggest", tags=["ai"])
def ai_suggest(content: str, db: Session = Depends(get_db)):
    """KB-grounded suggest: retrieval + DeepSeek rewrite when HF_TOKEN is set (webchat + inbox)."""
    from app.services.ai_llm import grounded_answer
    from app.services.ai_stub import suggest_reply

    base = suggest_reply(db, content)
    # If HF is configured, add a KB-grounded LLM draft (same grounding as web auto-reply)
    articles = [{"title": s["title"], "body": s["body"], "category": "General"} for s in base.get("suggestions", [])]
    # Fall back to letting the LLM learn directly from the KB if no suggestions
    draft = grounded_answer(content, articles, db=db) if articles else None
    if not draft and not articles:
        draft = grounded_answer(content, [], db=db)
    if draft:
        base["llm_draft"] = draft
        base["llm_model"] = __import__("os").environ.get("HF_MODEL", "deepseek-ai/DeepSeek-V4.1-Flash")
    return base
