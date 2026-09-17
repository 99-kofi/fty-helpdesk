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
    """Phase-4 stub: keyword retrieval from knowledge base (no LLM yet)."""
    from app.services.ai_stub import suggest_reply
    return suggest_reply(db, content)
