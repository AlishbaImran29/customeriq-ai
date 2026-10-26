"""Auto Messenger part 4: products to announce, campaigns, and who each campaign is sent to."""

import datetime as dt
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

CAMPAIGN_STATUSES = ("draft", "approved", "sending", "completed", "cancelled")


class CatalogProduct(TimestampMixin, Base):
    """A product the seller wants to tell customers about: typed in or created by a Shopify webhook."""

    __tablename__ = "catalog_products"
    __table_args__ = (
        CheckConstraint("source IN ('manual', 'shopify', 'launch_studio')", name="catalog_source_known"),
        CheckConstraint("price IS NULL OR price >= 0", name="catalog_price_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(100))
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    description: Mapped[str | None] = mapped_column(Text)                    # facts the seller gives; the AI may use ONLY these
    image_url: Mapped[str | None] = mapped_column(String(500))                # shown in emails
    product_url: Mapped[str | None] = mapped_column(String(500))              # where Shop now goes
    source: Mapped[str] = mapped_column(String(14), default="manual", server_default="manual")
    external_id: Mapped[str | None] = mapped_column(String(60), unique=True)   # Shopify's product id


class Campaign(TimestampMixin, Base):
    """One announcement of a product. It starts as a DRAFT; nothing is sent until the seller approves it."""

    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'approved', 'sending', 'completed', 'cancelled')", name="campaign_status_known"),
        CheckConstraint("early_access_hours >= 0", name="campaign_early_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_products.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="draft", server_default="draft", index=True)
    # Who gets it: {"categories": ["Shoes"], "segments": ["Champions"], "include_category_buyers": true}
    audience: Mapped[dict] = mapped_column(JSONB)
    offer_text: Mapped[str | None] = mapped_column(String(300))             # the only offer the messages may mention
    early_access_hours: Mapped[int] = mapped_column(Integer, default=24, server_default="24")
    # {"messages": {"champions": {"en": "...", "ur": "..."}}, "subject": {"en": "...", "ur": "..."}}
    messages: Mapped[dict | None] = mapped_column(JSONB)
    ai_draft: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")     # the wording is still the AI's draft
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class CampaignRecipient(TimestampMixin, Base):
    """One customer of one campaign, with when they are to be messaged: Champions first, the rest later."""

    __tablename__ = "campaign_recipients"
    __table_args__ = (
        UniqueConstraint("campaign_id", "customer_id", name="uq_campaign_recipients_campaign_customer"),
        CheckConstraint("stage IN ('early', 'regular')", name="recipient_stage_known"),
        CheckConstraint("status IN ('pending', 'sent', 'skipped')", name="recipient_status_known"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    segment: Mapped[str] = mapped_column(String(30))                         # champions, loyal, potential, at_risk, lost
    stage: Mapped[str] = mapped_column(String(8))
    scheduled_for: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(8), default="pending", server_default="pending", index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(String(100))                  # why it was skipped
