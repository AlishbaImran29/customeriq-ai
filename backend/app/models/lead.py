import datetime as dt

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

STAGES = ("new", "contacted", "interested", "converted", "lost")
SOURCES = ("manual", "website_form", "meta_lead_ad", "click_to_whatsapp")


class Lead(TimestampMixin, Base):
    """Someone who showed interest but has not bought yet. A lead is never deleted when it converts: it is linked to the customer
    it became, so where the customer came from (source, campaign, UTM) and the whole history stay."""

    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint("stage IN ('new', 'contacted', 'interested', 'converted', 'lost')", name="lead_stage_known"),
        CheckConstraint("source IN ('manual', 'website_form', 'meta_lead_ad', 'click_to_whatsapp')", name="lead_source_known"),
        CheckConstraint("phone_normalised IS NOT NULL OR email IS NOT NULL", name="lead_has_contact"),
        Index("uq_leads_external_ref", "external_ref", unique=True, postgresql_where=text("external_ref IS NOT NULL")),
        Index("ix_leads_stage_created", "stage", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(40))
    phone_normalised: Mapped[str | None] = mapped_column(String(13), index=True)
    email: Mapped[str | None] = mapped_column(String(320))
    source: Mapped[str] = mapped_column(String(20), default="manual")
    campaign: Mapped[str | None] = mapped_column(String(160))
    utm_source: Mapped[str | None] = mapped_column(String(100))
    utm_medium: Mapped[str | None] = mapped_column(String(100))
    utm_campaign: Mapped[str | None] = mapped_column(String(160))
    product_interest: Mapped[str | None] = mapped_column(String(200))
    stage: Mapped[str] = mapped_column(String(12), default="new", server_default="new")
    notes: Mapped[str | None] = mapped_column(Text)
    lost_reason: Mapped[str | None] = mapped_column(String(200))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    external_ref: Mapped[str | None] = mapped_column(String(100))        # Meta's leadgen id: the same lead is never saved twice
    follow_up_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    contacted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    sla_alerted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class LeadEvent(Base):
    """The lead's history: created, moved to a stage, converted, note added."""

    __tablename__ = "lead_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(30))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
