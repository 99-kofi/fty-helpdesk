from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="agent")  # admin|manager|agent
    team: Mapped[str | None] = mapped_column(String(80), nullable=True)  # legacy primary team label
    availability: Mapped[str] = mapped_column(String(20), default="available")  # available|away|offline
    max_active: Mapped[int] = mapped_column(default=10)  # workload capacity (spec §7)
