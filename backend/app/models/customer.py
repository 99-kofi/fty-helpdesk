from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    identities: Mapped[list["CustomerIdentity"]] = relationship(back_populates="customer", cascade="all, delete-orphan")


class CustomerIdentity(Base):
    """One row per (channel, external_user_id) — foundation of omnichannel resolution."""
    __tablename__ = "customer_identities"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(20), index=True)  # instagram|whatsapp|...
    external_user_id: Mapped[str] = mapped_column(String(255), index=True)
    meta: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer: Mapped[Customer] = relationship(back_populates="identities")
