"""Returns, refunds and complaints.

A RETURN REQUEST is a customer asking to send something back. The seller approves or rejects it, marks the goods received,
and decides whether they go back on the shelf. A REFUND is recorded SEPARATELY: the app never moves money, it only keeps
the seller's note that a refund was asked for and, later, that they paid it. A TICKET is a complaint or question to follow up."""

import datetime as dt
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ReturnRequest(TimestampMixin, Base):
    __tablename__ = "return_requests"
    __table_args__ = (
        CheckConstraint("status IN ('requested', 'approved', 'rejected', 'received', 'closed')", name="return_status_known"),
        CheckConstraint("resolution IS NULL OR resolution IN ('refund', 'replacement', 'none')", name="return_resolution_known"),
        Index("ix_return_requests_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10), default="requested", server_default="requested")
    resolution: Mapped[str | None] = mapped_column(String(12))
    decision_note: Mapped[str | None] = mapped_column(String(300))
    restocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    replacement_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class ReturnEvidence(Base):
    """A photo or short video the customer (or seller) attached, kept in a PRIVATE storage bucket."""

    __tablename__ = "return_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(ForeignKey("return_requests.id", ondelete="CASCADE"), index=True)
    storage_path: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(10))
    mime_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=sql_text("now()"))


class ReturnEvent(Base):
    """The audit history of a return: every decision and who/what it affected. Only ever added to."""

    __tablename__ = "return_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(ForeignKey("return_requests.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(30))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    by: Mapped[str | None] = mapped_column(String(320))
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=sql_text("now()"))


class Refund(TimestampMixin, Base):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("status IN ('requested', 'recorded')", name="refund_status_known"),
        CheckConstraint("amount >= 0", name="refund_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int | None] = mapped_column(ForeignKey("return_requests.id", ondelete="SET NULL"), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(10), default="requested", server_default="requested")
    method: Mapped[str | None] = mapped_column(String(60))        # how the seller paid it back (JazzCash, bank transfer...)
    reference: Mapped[str | None] = mapped_column(String(100))   # the seller's own note, such as a transaction number
    recorded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_by: Mapped[str | None] = mapped_column(String(320))


class Ticket(TimestampMixin, Base):
    """A complaint or question to follow up, with an owner and a status."""

    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'in_progress', 'resolved', 'closed')", name="ticket_status_known"),
        CheckConstraint("priority IN ('low', 'normal', 'high')", name="ticket_priority_known"),
        Index("ix_tickets_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="open", server_default="open")
    priority: Mapped[str] = mapped_column(String(8), default="normal", server_default="normal")
    assigned_to: Mapped[str | None] = mapped_column(String(320))
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class TicketNote(Base):
    __tablename__ = "ticket_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    author: Mapped[str | None] = mapped_column(String(320))
    text: Mapped[str] = mapped_column(Text)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=sql_text("now()"))
