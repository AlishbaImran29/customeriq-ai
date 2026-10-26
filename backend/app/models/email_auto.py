"""Email Automations: the shop's email look, COD email answers, the log of every email sent, and product announcement drafts."""

import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

COD_EMAIL_STATUSES = ("pending", "confirmed", "cancelled")
EMAIL_KINDS = ("cod", "cod_reminder", "winback", "new_product", "test")
LIFECYCLE = ("active", "at_risk", "lost")


class EmailSettings(TimestampMixin, Base):
    """One row: how the shop looks in emails. Empty fields fall back to sensible defaults."""

    __tablename__ = "email_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_name: Mapped[str | None] = mapped_column(String(80))
    logo_url: Mapped[str | None] = mapped_column(String(400))
    brand_color: Mapped[str | None] = mapped_column(String(7))
    support_email: Mapped[str | None] = mapped_column(String(320))
    store_url: Mapped[str | None] = mapped_column(String(300))


class CodEmail(TimestampMixin, Base):
    """The answer to the "please confirm your order" email: pending until the customer presses a button."""

    __tablename__ = "cod_emails"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_cod_emails_order"),
        CheckConstraint("status IN ('pending', 'confirmed', 'cancelled')", name="cod_email_status_known"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(10), default="pending", server_default="pending")
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class EmailLog(Base):
    """Every email this module tried to send. Used for the daily limit, the 30-day win-back rule and "sent once"."""

    __tablename__ = "email_log"
    __table_args__ = (
        CheckConstraint("kind IN ('cod', 'cod_reminder', 'winback', 'new_product', 'test')", name="email_log_kind_known"),
        CheckConstraint("status IN ('sent', 'mock', 'failed')", name="email_log_status_known"),
        Index("ix_email_log_customer_kind", "customer_id", "kind", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    to_email: Mapped[str] = mapped_column(String(320))
    kind: Mapped[str] = mapped_column(String(14))
    subject: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(8))
    error: Mapped[str | None] = mapped_column(String(200))
    ref_id: Mapped[int | None] = mapped_column(Integer)                  # the order id (COD) or the announcement id
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)


class EmailAnnouncement(TimestampMixin, Base):
    """A new-product email: a draft until the seller previews it and presses Send."""

    __tablename__ = "email_announcements"
    __table_args__ = (CheckConstraint("status IN ('draft', 'sent')", name="email_announcement_status_known"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("catalog_products.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(6), default="draft", server_default="draft")
    sent_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
