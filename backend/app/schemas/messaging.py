"""Request and response shapes of the Auto Messenger (camelCase, matching frontend/lib/api/messaging.ts)."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.imports import CamelModel

Channel = Literal["whatsapp", "email"]
Category = Literal["utility", "marketing"]
Language = Literal["ur", "en"]
MetaStatus = Literal["not_submitted", "pending", "approved", "rejected"]


# --- settings ---------------------------------------------------------------------------------------------


class ConnectionOut(CamelModel):
    configured: bool
    details: dict[str, bool]           # which pieces are set (never their values)
    provider: str | None = None        # email: webhook, brevo or smtp


class ConsentCountOut(CamelModel):
    opted_in: int
    opted_out: int
    not_asked: int


class SettingsOut(CamelModel):
    dry_run: bool                      # the toggle the seller set
    dry_run_forced: bool               # the server says dry run: the toggle cannot turn it off
    effective_dry_run: bool            # what really happens
    quiet_start: str                   # "21:00"
    quiet_end: str                     # "10:00"
    timezone: str
    weekly_marketing_cap: int
    default_language: Language
    store_name: str | None
    review_url: str | None
    cost_utility: float | None
    cost_marketing: float | None
    campaign_batch_size: int
    early_access_hours: int
    holdout_percent: int
    whatsapp: ConnectionOut
    email: ConnectionOut
    unsubscribe_ready: bool            # MESSAGING_SECRET and PUBLIC_API_URL are set
    webhook_url: str | None            # what to paste into Meta
    consent: dict[str, ConsentCountOut]
    development: bool                  # not production: the demo helpers (pretend a customer replied) are available
    scheduler_ready: bool              # SCHEDULER_SECRET is set, so a scheduler can call the server
    shopify_ready: bool                # the Shopify webhook secret is set


class SettingsIn(CamelModel):
    """Only the fields that are sent are changed."""

    dry_run: bool | None = None
    quiet_start: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_end: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekly_marketing_cap: int | None = Field(default=None, ge=0, le=14)
    default_language: Language | None = None
    store_name: str | None = Field(default=None, max_length=80)
    review_url: str | None = Field(default=None, max_length=300)
    cost_utility: float | None = Field(default=None, ge=0, le=1000)
    cost_marketing: float | None = Field(default=None, ge=0, le=1000)
    campaign_batch_size: int | None = Field(default=None, ge=1, le=500)
    early_access_hours: int | None = Field(default=None, ge=0, le=168)
    holdout_percent: int | None = Field(default=None, ge=0, le=50)


class TestSendIn(CamelModel):
    channel: Channel
    to: str | None = Field(default=None, max_length=40)       # WhatsApp: a Pakistani mobile number. Email: always your own address.
    language: Language = "en"


class TestSendOut(CamelModel):
    ok: bool
    dry_run: bool
    error: str | None
    sent_to: str                       # masked


# --- templates ---------------------------------------------------------------------------------------------


class TemplateIn(CamelModel):
    name: str = Field(min_length=3, max_length=80)
    channel: Channel
    category: Category
    language: Language
    event: str | None = Field(default=None, max_length=40)
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=1, max_length=2000)
    meta_template_name: str | None = Field(default=None, max_length=100)


class TemplatePatch(CamelModel):
    name: str | None = Field(default=None, min_length=3, max_length=80)
    category: Category | None = None
    event: str | None = Field(default=None, max_length=40)
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=2000)
    meta_template_name: str | None = Field(default=None, max_length=100)
    meta_approval_status: MetaStatus | None = None


class TemplateOut(CamelModel):
    id: int
    name: str
    channel: Channel
    category: Category
    language: Language
    event: str | None
    subject: str | None
    body: str
    variables: list[str]
    meta_template_name: str | None
    meta_approval_status: MetaStatus
    approved_by_seller: bool
    approved_at: datetime | None
    is_default: bool


class PreviewIn(CamelModel):
    body: str = Field(max_length=2000)
    subject: str | None = Field(default=None, max_length=200)
    language: Language = "en"


class PreviewOut(CamelModel):
    label: Literal["Example values, not a real customer"] = "Example values, not a real customer"
    text: str | None
    subject: str | None
    variables: list[str]
    meta_body: str                     # the body as Meta wants it ({{1}}, {{2}})
    meta_variables: list[str]          # which variable is {{1}}, {{2}}...
    error: str | None


class VariableOut(CamelModel):
    name: str
    description: str
    optional: bool


# --- consent -----------------------------------------------------------------------------------------------


class ChannelConsentOut(CamelModel):
    state: Literal["opted_in", "opted_out", "none"]
    changed_on: date | None
    source: str | None


class ConsentCustomerOut(CamelModel):
    id: int
    name: str
    phone: str | None
    email: str | None
    whatsapp: ChannelConsentOut
    email_consent: ChannelConsentOut


class ConsentPage(CamelModel):
    total: int
    customers: list[ConsentCustomerOut]


class ConsentChangeIn(CamelModel):
    channel: Channel
    opted_in: bool
    note: str | None = Field(default=None, max_length=200)


class ConsentImportOut(CamelModel):
    rows_in_file: int
    changed: int
    unchanged: int
    not_found: int
    rejected: int
    errors: list[dict]


# --- messages -----------------------------------------------------------------------------------------------


class MessageOut(CamelModel):
    id: int
    customer_id: int
    customer_name: str
    channel: Channel
    category: Category
    subject: str | None
    text: str
    status: Literal["queued", "sent", "delivered", "read", "failed", "replied", "skipped"]
    error: str | None
    attempts: int
    dry_run: bool
    template_name: str | None
    campaign_id: int | None
    journey_id: int | None
    order_id: int | None
    queued_at: datetime
    sent_at: datetime | None
    next_attempt_at: datetime | None


class IncomingOut(CamelModel):
    id: int
    customer_name: str | None
    from_address: str
    message_type: str
    body: str | None
    is_stop: bool
    answer: str | None
    received_at: datetime


class QueueOut(CamelModel):
    processed: int
    sent: int
    requeued: int
    failed: int
    skipped: int


class SimulateIncomingIn(CamelModel):
    phone: str = Field(max_length=40)
    text: str = Field(max_length=500)


class SimulateStatusIn(CamelModel):
    message_id: int
    status: Literal["sent", "delivered", "read", "failed"]

