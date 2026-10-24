"""Auto Messenger tables (part 1): who agreed to be messaged, the message templates, every message sent
or not sent, the replies that came in, and the seller's messaging settings.

RULE 1 of the feature lives here as data: a customer can only be messaged on a channel if their row in
`customer_consent` says opted_in. Every change is also written to `consent_events`, an append-only history,
so the seller can always show WHEN and HOW a customer agreed (or stopped).
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

CHANNELS = ("whatsapp", "email")
CATEGORIES = ("utility", "marketing")             # utility = order updates, marketing = everything else
STATUSES = ("queued", "sent", "delivered", "read", "failed", "replied", "skipped")
META_STATUSES = ("not_submitted", "pending", "approved", "rejected")


class CustomerConsent(TimestampMixin, Base):
    """The CURRENT consent of one customer on one channel."""

    __tablename__ = "customer_consent"
    __table_args__ = (
        UniqueConstraint("customer_id", "channel", name="uq_customer_consent_customer_channel"),
        CheckConstraint("channel IN ('whatsapp', 'email')", name="consent_channel_known"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(10))
    opted_in: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    changed_on: Mapped[dt.date] = mapped_column(Date)                    # the day it last changed
    source: Mapped[str] = mapped_column(String(40))                      # manual, import, add_order, shopify, whatsapp_stop, email_unsubscribe...


class ConsentEvent(Base):
    """One entry of the consent history. Never edited or deleted (except with the customer)."""

    __tablename__ = "consent_events"
    __table_args__ = (CheckConstraint("action IN ('opt_in', 'opt_out')", name="consent_action_known"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(10))
    action: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(200))
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class MessageTemplate(TimestampMixin, Base):
    """The wording of a message, with {{variables}}. Nothing is sent from a template the seller has not approved.

    `event` says which automatic message it is for ("order_dispatched", "journey_at_risk_1"...), empty for
    one-off templates. For WhatsApp, a business-initiated message needs a template approved BY META:
    `meta_template_name` is its name there and `meta_approval_status` what Meta said.
    """

    __tablename__ = "message_templates"
    __table_args__ = (
        UniqueConstraint("name", "channel", "language", name="uq_message_templates_name_channel_language"),
        CheckConstraint("channel IN ('whatsapp', 'email')", name="template_channel_known"),
        CheckConstraint("category IN ('utility', 'marketing')", name="template_category_known"),
        CheckConstraint("language IN ('ur', 'en')", name="template_language_known"),
        CheckConstraint("meta_approval_status IN ('not_submitted', 'pending', 'approved', 'rejected')", name="template_meta_status_known"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    channel: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(10))
    language: Mapped[str] = mapped_column(String(2))
    event: Mapped[str | None] = mapped_column(String(40), index=True)
    subject: Mapped[str | None] = mapped_column(String(200))             # email only
    body: Mapped[str] = mapped_column(Text)
    meta_template_name: Mapped[str | None] = mapped_column(String(100))
    meta_approval_status: Mapped[str] = mapped_column(String(14), default="not_submitted", server_default="not_submitted")
    approved_by_seller: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")      # made by "add the default templates"


class Message(TimestampMixin, Base):
    """One message to one customer: sent, or the record of why it was not."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'sent', 'delivered', 'read', 'failed', 'replied', 'skipped')", name="message_status_known"),
        CheckConstraint("channel IN ('whatsapp', 'email')", name="message_channel_known"),
        CheckConstraint("category IN ('utility', 'marketing')", name="message_category_known"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(10))
    template_id: Mapped[int | None] = mapped_column(ForeignKey("message_templates.id", ondelete="SET NULL"), index=True)
    category: Mapped[str] = mapped_column(String(10))
    subject: Mapped[str | None] = mapped_column(String(200))
    rendered_text: Mapped[str] = mapped_column(Text)
    variables: Mapped[dict | None] = mapped_column(JSONB)                # the values that were filled in, kept so a retry sends the same thing
    status: Mapped[str] = mapped_column(String(10), default="queued", server_default="queued", index=True)
    error: Mapped[str | None] = mapped_column(String(200))               # a short code, such as no_consent or whatsapp_131030
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    # One message per customer + channel + event, ever: this key is UNIQUE (see services/messaging/service.py).
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), index=True)
    # Where it came from. campaign_id and journey_id are plain numbers (their tables come in later parts).
    campaign_id: Mapped[int | None] = mapped_column(Integer, index=True)
    journey_id: Mapped[int | None] = mapped_column(Integer, index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), index=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    queued_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    replied_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class IncomingMessage(Base):
    """A message a customer sent to the seller's WhatsApp number."""

    __tablename__ = "incoming_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    channel: Mapped[str] = mapped_column(String(10), default="whatsapp", server_default="whatsapp")
    from_address: Mapped[str] = mapped_column(String(40))                 # +923001234567
    provider_message_id: Mapped[str] = mapped_column(String(128), unique=True)
    message_type: Mapped[str] = mapped_column(String(20))                 # text, image, video, other
    body: Mapped[str | None] = mapped_column(Text)
    media_id: Mapped[str | None] = mapped_column(String(128))
    mime_type: Mapped[str | None] = mapped_column(String(80))
    received_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    is_stop: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    answer: Mapped[str | None] = mapped_column(String(3))                 # yes / no, when the text was a clear answer


class MessagingSettings(TimestampMixin, Base):
    """The seller's messaging settings: always exactly one row (id 1)."""

    __tablename__ = "messaging_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")     # safe by default: nothing real is sent
    quiet_start: Mapped[dt.time] = mapped_column(default=dt.time(21, 0))
    quiet_end: Mapped[dt.time] = mapped_column(default=dt.time(10, 0))
    timezone: Mapped[str] = mapped_column(String(40), default="Asia/Karachi", server_default="Asia/Karachi")
    weekly_marketing_cap: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    default_language: Mapped[str] = mapped_column(String(2), default="en", server_default="en")
    store_name: Mapped[str | None] = mapped_column(String(80))
    review_url: Mapped[str | None] = mapped_column(String(300))
    # The seller's own prices per WhatsApp message (never hard-coded here): rupees; None = not entered.
    cost_utility: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    cost_marketing: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    campaign_batch_size: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    early_access_hours: Mapped[int] = mapped_column(Integer, default=24, server_default="24")
    holdout_percent: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
