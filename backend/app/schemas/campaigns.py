"""Shapes for products and campaigns (Auto Messenger part 4), camelCase."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.imports import CamelModel

Segment = Literal["Champions", "Loyal Customers", "Potential Loyalists", "At-Risk Customers", "Lost Customers"]


class ProductIn(CamelModel):
    name: str = Field(min_length=2, max_length=120)
    category: str | None = Field(default=None, max_length=100)
    price: float | None = Field(default=None, ge=0, le=100_000_000)
    description: str | None = Field(default=None, max_length=2000)


class ProductOut(CamelModel):
    id: int
    name: str
    category: str | None
    price: float | None
    description: str | None
    source: str
    campaign_id: int | None


class AudienceConfig(CamelModel):
    categories: list[str] = Field(default_factory=list, max_length=10)
    segments: list[Segment] = Field(default_factory=list)
    include_category_buyers: bool = True


class CampaignPatch(CamelModel):
    """Only the fields that are sent are changed. A campaign can be changed only while it is a draft."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    audience: AudienceConfig | None = None
    offer_text: str | None = Field(default=None, max_length=300)
    early_access_hours: int | None = Field(default=None, ge=0, le=168)


class SegmentMessage(CamelModel):
    en: str = Field(default="", max_length=700)
    ur: str = Field(default="", max_length=700)


class CampaignMessages(CamelModel):
    messages: dict[str, SegmentMessage]                 # keyed by champions, loyal, potential, at_risk, lost, other
    subject: SegmentMessage                             # the email subject, English and Urdu


class RecipientCounts(CamelModel):
    pending: int
    sent: int
    skipped: int
    total: int


class CampaignOut(CamelModel):
    id: int
    name: str
    status: Literal["draft", "approved", "sending", "completed", "cancelled"]
    product_id: int | None
    product_name: str | None
    audience: AudienceConfig
    offer_text: str | None
    early_access_hours: int
    messages: CampaignMessages | None
    ai_draft: bool                                       # the wording is still the AI's draft
    approved_at: datetime | None
    completed_at: datetime | None
    counts: RecipientCounts
    created_at: datetime


class AudienceOut(CamelModel):
    candidates: int
    eligible: int                                        # can really be messaged
    no_consent: int
    no_address: int
    by_segment: dict[str, int]
    truncated: bool


class SampleOut(CamelModel):
    customer_name: str
    segment: str
    channel: Literal["whatsapp", "email"]
    language: Literal["ur", "en"]
    text: str | None
    subject: str | None
    error: str | None


class PreviewOut(CamelModel):
    label: Literal["Real customers from your list: nothing has been sent"] = "Real customers from your list: nothing has been sent"
    audience: AudienceOut
    samples: list[SampleOut]


class DraftOut(CamelModel):
    label: Literal["AI draft"] = "AI draft"
    campaign: CampaignOut
    cached: bool
    model: str | None


class GenerateIn(CamelModel):
    force: bool = False


class ApproveOut(CamelModel):
    recipients: int
    early: int


class RecipientOut(CamelModel):
    id: int
    customer_name: str
    segment: str
    stage: Literal["early", "regular"]
    scheduled_for: datetime
    status: Literal["pending", "sent", "skipped"]
    reason: str | None
    message_status: str | None
