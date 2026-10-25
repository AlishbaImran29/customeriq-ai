import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Conversation(TimestampMixin, Base):
    """The seller's side of one customer's chat: who owns it, whether it is open, and how far they have read.
    The messages themselves already exist (`messages` going out, `incoming_messages` coming in)."""

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("customer_id", name="uq_conversations_customer"),
        CheckConstraint("status IN ('open', 'closed')", name="conversation_status_known"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(8), default="open", server_default="open")
    assigned_to: Mapped[str | None] = mapped_column(String(320))
    last_read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class InboxNote(Base):
    """An internal note on a conversation. The customer never sees it."""

    __tablename__ = "inbox_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    author: Mapped[str | None] = mapped_column(String(320))
    body: Mapped[str] = mapped_column(Text)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class FaqEntry(TimestampMixin, Base):
    """A policy or answer the seller typed (delivery time, return window...). Suggested replies may use ONLY these, orders and products."""

    __tablename__ = "faq_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    keywords: Mapped[str] = mapped_column(String(300))        # words (English or Roman Urdu) that bring this answer up, separated by commas
    answer: Mapped[str] = mapped_column(Text)
