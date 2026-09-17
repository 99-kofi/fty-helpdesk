from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class AssignmentHistory(Base):
    """Full audit trail: who assigned/reassigned whom, when, why (spec §10)."""
    __tablename__ = "assignment_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(30), index=True)  # triaged|assigned|reassigned|priority_changed|status_changed|unassigned
    from_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    from_team: Mapped[str | None] = mapped_column(String(80), nullable=True)
    to_team: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)  # e.g. "NORMAL → HIGH"
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_by: Mapped[str] = mapped_column(String(80), default="auto")  # auto|manager name|agent name|api
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
