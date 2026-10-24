"""New product announcements (Auto Messenger part 4).

THE FLOW
  1. A product is added (the form, a Shopify "products/create" webhook, or Launch Studio) -> a DRAFT campaign is made.
  2. The audience is worked out: customers who bought from the same category before, plus the segments the seller
     chose (Champions by default). Customers who have not agreed to a channel are left out and counted.
  3. The AI writes ONE base message per segment, in English and Urdu (campaign_ai.py): one AI call for the whole
     campaign, not one per customer. Variables are filled in per customer (name, last purchase, ...).
  4. The seller sees 5 sample messages with real names, edits the wording, and APPROVES. Only then are templates made
     and recipients scheduled; before that, nothing can be sent.
  5. Champions are messaged first (early access); everyone else `early_access_hours` later (default 24). The sending
     runs in small batches (default 30 per pass), so a big audience never goes out in one burst.
Each customer gets at most one message per campaign: WhatsApp if they agreed to it and have a number, else email.
The usual checks (consent, weekly cap, quiet hours, "never twice") still apply to every message.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import Campaign, CampaignRecipient, CatalogProduct, Customer, CustomerConsent, MessageTemplate, MessagingSettings, Order
from app.services.analytics_data import load_snapshot
from app.services.messaging import service
from app.services.messaging.render import check_template_text, render
from app.services.messaging.settings_store import get_row
from app.services.order_status import customer_language, money

logger = logging.getLogger(__name__)

SEGMENT_KEYS = {
    "Champions": "champions", "Loyal Customers": "loyal", "Potential Loyalists": "potential",
    "At-Risk Customers": "at_risk", "Lost Customers": "lost",
}
OTHER = "other"                                          # customers without a segment (too few customers to segment)
SEGMENT_LABELS = {v: k for k, v in SEGMENT_KEYS.items()} | {OTHER: "Customers"}
EARLY_SEGMENT = "champions"
LANGUAGES = ("en", "ur")
CHANNELS = ("whatsapp", "email")
STOP_LINE = {"en": "Reply STOP to stop messages.", "ur": "پیغامات بند کرنے کے لیے STOP لکھیں۔"}
PREVIEW_SAMPLES = 5
MAX_AUDIENCE = 5000                                      # a safety limit for one campaign


def segment_key(label: str | None) -> str:
    return SEGMENT_KEYS.get(label or "", OTHER)


def template_name(campaign_id: int, key: str, language: str, channel: str) -> str:
    return f"campaign_{campaign_id}_{key}_{language}" + ("_email" if channel == "email" else "")


# --- products and drafts ----------------------------------------------------------------------------------------------


def create_product(
    db: Session, *, name: str, category: str | None, price: Decimal | None, description: str | None, source: str,
    external_id: str | None = None, launch_project_id: int | None = None,
) -> tuple[CatalogProduct, Campaign]:
    """Save a product and make its DRAFT campaign. Nothing is sent. A Shopify product that is already known is returned as is."""
    if external_id:
        known = db.scalar(select(CatalogProduct).where(CatalogProduct.external_id == external_id))
        if known is not None:
            campaign = db.scalar(select(Campaign).where(Campaign.product_id == known.id).order_by(Campaign.id).limit(1))
            if campaign is not None:
                return known, campaign
    product = CatalogProduct(
        name=name.strip()[:120], category=(category or "").strip()[:100] or None, price=price, description=(description or "").strip() or None,
        source=source, external_id=external_id, launch_project_id=launch_project_id,
    )
    db.add(product)
    db.flush()
    return product, create_draft_campaign(db, product)


def create_draft_campaign(db: Session, product: CatalogProduct) -> Campaign:
    row = get_row(db)
    campaign = Campaign(
        name=f"New: {product.name}"[:120], product_id=product.id, status="draft",
        audience={"categories": [product.category] if product.category else [], "segments": ["Champions"], "include_category_buyers": True},
        early_access_hours=row.early_access_hours,
    )
    db.add(campaign)
    db.flush()
    return campaign


# --- the audience --------------------------------------------------------------------------------------------------------


@dataclass
class Member:
    customer: Customer
    segment: str                                        # champions, loyal, ...
    channel: str                                        # whatsapp or email


@dataclass
class Audience:
    members: list[Member] = field(default_factory=list)
    candidates: int = 0
    no_consent: int = 0                                 # asked for, but never agreed on any channel
    no_address: int = 0                                 # agreed, but there is no number / email to use
    truncated: bool = False

    def by_segment(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for m in self.members:
            counts[m.segment] = counts.get(m.segment, 0) + 1
        return counts


def segment_by_customer(db: Session) -> dict[int, str]:
    """Customer id -> segment key, from the same segmentation the dashboard shows."""
    snapshot = load_snapshot(db)
    if snapshot.empty:
        return {}
    by_external = {c.customer_id: segment_key(c.segment) for c in snapshot.customers}
    if not by_external:
        return {}
    ids = {}
    external_ids = list(by_external)
    for start in range(0, len(external_ids), 1000):
        for cid, ext in db.execute(select(Customer.id, Customer.external_id).where(Customer.external_id.in_(external_ids[start:start + 1000]))):
            ids[cid] = by_external[ext]
    return ids


def pick_channel(db_consent: dict[tuple[int, str], bool], customer: Customer) -> str | None:
    """WhatsApp when the customer agreed and has a number; otherwise email when they agreed and have a real address."""
    for channel in CHANNELS:
        if db_consent.get((customer.id, channel)) and service._address(customer, channel):          # noqa: SLF001 (the one place that knows what a usable address is)
            return channel
    return None


def compute_audience(db: Session, campaign: Campaign) -> Audience:
    config = campaign.audience or {}
    categories = [c.strip().lower() for c in config.get("categories", []) if isinstance(c, str) and c.strip()]
    segments = {SEGMENT_KEYS[s] for s in config.get("segments", []) if s in SEGMENT_KEYS}
    segment_of = segment_by_customer(db)
    ids: set[int] = {cid for cid, seg in segment_of.items() if seg in segments}
    if config.get("include_category_buyers", True) and categories:
        ids |= set(db.scalars(select(Order.customer_id).where(func.lower(Order.product_category).in_(categories)).distinct()))
    audience = Audience(candidates=len(ids))
    if not ids:
        return audience
    ordered = sorted(ids)
    if len(ordered) > MAX_AUDIENCE:
        ordered, audience.truncated = ordered[:MAX_AUDIENCE], True
    consent: dict[tuple[int, str], bool] = {}
    customers: list[Customer] = []
    for start in range(0, len(ordered), 1000):
        chunk = ordered[start:start + 1000]
        customers += list(db.scalars(select(Customer).where(Customer.id.in_(chunk)).order_by(Customer.id)))
        for row in db.scalars(select(CustomerConsent).where(CustomerConsent.customer_id.in_(chunk))):
            consent[(row.customer_id, row.channel)] = row.opted_in
    for customer in customers:
        if not any(consent.get((customer.id, ch)) for ch in CHANNELS):
            audience.no_consent += 1
            continue
        channel = pick_channel(consent, customer)
        if channel is None:
            audience.no_address += 1
            continue
        audience.members.append(Member(customer, segment_of.get(customer.id, OTHER), channel))
    return audience


# --- per-customer values ------------------------------------------------------------------------------------------------------


def last_purchase(db: Session, customer_id: int) -> tuple[str | None, str | None]:
    """(the first product of the customer's latest order, that order's category)."""
    row = db.execute(select(Order.products, Order.product_category).where(Order.customer_id == customer_id).order_by(Order.order_date.desc(), Order.id.desc()).limit(1)).first()
    if row is None:
        return None, None
    product = (row[0] or "").split(",")[0].strip() or None
    return product, row[1]


def campaign_variables(db: Session, customer: Customer, product: CatalogProduct | None, campaign: Campaign, row: MessagingSettings, language: str, segment: str) -> dict[str, str | None]:
    last_product, last_category = last_purchase(db, customer.id)
    line = None
    if last_product:
        line = f"Last time you bought {last_product}." if language == "en" else f"پچھلی بار آپ نے {last_product} خریدا تھا۔"
    extra = {
        "product_name": product.name if product else campaign.name, "price": money(product.price) if product and product.price is not None else None,
        "category": product.category if product else None, "offer_text": campaign.offer_text, "last_product": last_product,
        "last_category": last_category, "last_purchase_line": line, "segment": SEGMENT_LABELS.get(segment),
    }
    return service.customer_variables(customer, row, language, extra)


def message_text(campaign: Campaign, segment: str, language: str) -> str | None:
    messages = (campaign.messages or {}).get("messages", {})
    return (messages.get(segment) or messages.get(OTHER) or {}).get(language)


def email_subject(campaign: Campaign, language: str) -> str:
    subjects = (campaign.messages or {}).get("subject", {})
    return subjects.get(language) or subjects.get("en") or campaign.name


@dataclass
class Sample:
    customer_name: str
    segment: str
    channel: str
    language: str
    text: str | None
    subject: str | None
    error: str | None = None


def preview(db: Session, campaign: Campaign, audience: Audience | None = None) -> tuple[list[Sample], Audience]:
    """Up to 5 sample messages, one per segment first, rendered for real customers so the seller sees what goes out."""
    audience = audience or compute_audience(db, campaign)
    product = db.get(CatalogProduct, campaign.product_id) if campaign.product_id else None
    row = get_row(db)
    chosen: list[Member] = []
    seen: set[str] = set()
    for member in audience.members:                      # one customer of each segment first...
        if member.segment not in seen:
            seen.add(member.segment)
            chosen.append(member)
    for member in audience.members:                      # ...then more to make up 5
        if len(chosen) >= PREVIEW_SAMPLES:
            break
        if member not in chosen:
            chosen.append(member)
    samples = []
    for member in chosen[:PREVIEW_SAMPLES]:
        language = customer_language(member.customer, row.default_language)
        name = " ".join(p for p in (member.customer.first_name, member.customer.last_name) if p) or member.customer.external_id
        body = message_text(campaign, member.segment, language)
        if body is None:
            samples.append(Sample(name, member.segment, member.channel, language, None, None, "No message written for this segment yet."))
            continue
        try:
            values = campaign_variables(db, member.customer, product, campaign, row, language, member.segment)
            text = render(_with_stop(body, language, member.channel), values)
            subject = render(email_subject(campaign, language), values) if member.channel == "email" else None
            samples.append(Sample(name, member.segment, member.channel, language, text, subject))
        except Exception as error:  # noqa: BLE001 (a missing variable must be SHOWN, not hidden)
            samples.append(Sample(name, member.segment, member.channel, language, None, None, f"Cannot be filled in for this customer: {getattr(error, 'name', error)}"))
    return samples, audience


# --- approval and sending --------------------------------------------------------------------------------------------------------


def _with_stop(body: str, language: str, channel: str) -> str:
    """WhatsApp marketing must say how to stop. (Email gets an unsubscribe link added automatically.)"""
    if channel == "whatsapp" and "stop" not in body.casefold():
        return f"{body}\n\n{STOP_LINE[language]}"
    return body


def validate_messages(campaign: Campaign, segments: set[str]) -> None:
    """Every segment in the audience needs a message in both languages, using only known variables."""
    for key in sorted(segments):
        for language in LANGUAGES:
            text = message_text(campaign, key, language)
            if not text or not text.strip():
                raise ApiError(422, "messages_missing", f"Write the {language.upper()} message for {SEGMENT_LABELS.get(key, key)} first.", {"segment": key, "language": language})
            check_template_text(text)
    for language in LANGUAGES:
        check_template_text("x", email_subject(campaign, language))


def approve(db: Session, campaign: Campaign, now: datetime | None = None) -> dict[str, int]:
    """The seller approves: make the templates (approved), schedule every recipient, and start sending. Commits nothing."""
    now = now or datetime.now(timezone.utc)
    if campaign.status != "draft":
        raise ApiError(409, "not_a_draft", "Only a draft campaign can be approved.")
    audience = compute_audience(db, campaign)
    if not audience.members:
        raise ApiError(422, "empty_audience", "Nobody in this audience has agreed to be messaged, so there is nobody to send to.")
    segments = {m.segment for m in audience.members}
    validate_messages(campaign, segments)
    for key in segments:
        for language in LANGUAGES:
            for channel in CHANNELS:
                name = template_name(campaign.id, key, language, channel)
                body = _with_stop(message_text(campaign, key, language) or "", language, channel)
                subject = email_subject(campaign, language) if channel == "email" else None
                template = db.scalar(select(MessageTemplate).where(MessageTemplate.name == name, MessageTemplate.channel == channel, MessageTemplate.language == language))
                if template is None:
                    template = MessageTemplate(name=name, channel=channel, category="marketing", language=language, event=f"campaign_{campaign.id}",
                                               meta_template_name=name if channel == "whatsapp" else None)
                    db.add(template)
                template.body, template.subject = body, subject
                template.approved_by_seller, template.approved_at = True, now
    early_hours = campaign.early_access_hours
    has_early = any(m.segment == EARLY_SEGMENT for m in audience.members) and early_hours > 0
    for member in audience.members:
        early = member.segment == EARLY_SEGMENT and has_early
        when = now if (early or not has_early) else now + timedelta(hours=early_hours)
        db.add(CampaignRecipient(campaign_id=campaign.id, customer_id=member.customer.id, segment=member.segment, stage="early" if early else "regular", scheduled_for=when))
    campaign.status, campaign.approved_at, campaign.ai_draft = "approved", now, False
    db.flush()
    return {"recipients": len(audience.members), "early": sum(1 for m in audience.members if m.segment == EARLY_SEGMENT and has_early)}


def send_due_batches(db: Session, settings: Settings, now: datetime | None = None) -> dict[str, int]:
    """Send the next batch of every running campaign: at most `campaign_batch_size` customers per campaign per pass."""
    now = now or datetime.now(timezone.utc)
    row = get_row(db)
    counts = {"campaigns": 0, "sent": 0, "skipped": 0}
    for campaign in db.scalars(select(Campaign).where(Campaign.status.in_(("approved", "sending"))).order_by(Campaign.id)):
        counts["campaigns"] += 1
        product = db.get(CatalogProduct, campaign.product_id) if campaign.product_id else None
        due = db.scalars(
            select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign.id, CampaignRecipient.status == "pending", CampaignRecipient.scheduled_for <= now)
            .order_by(CampaignRecipient.scheduled_for, CampaignRecipient.id).limit(row.campaign_batch_size)
        ).all()
        for recipient in due:
            _send_one(db, settings, campaign, product, recipient, row, now, counts)
        campaign.status = "sending"
        if not db.scalar(select(CampaignRecipient.id).where(CampaignRecipient.campaign_id == campaign.id, CampaignRecipient.status == "pending").limit(1)):
            campaign.status, campaign.completed_at = "completed", now
    return counts


def _send_one(db: Session, settings: Settings, campaign: Campaign, product: CatalogProduct | None, recipient: CampaignRecipient, row: MessagingSettings, now: datetime, counts: dict[str, int]) -> None:
    customer = db.get(Customer, recipient.customer_id)
    if customer is None:
        recipient.status, recipient.reason = "skipped", "customer_removed"
        counts["skipped"] += 1
        return
    consent = {(r.customer_id, r.channel): r.opted_in for r in db.scalars(select(CustomerConsent).where(CustomerConsent.customer_id == customer.id))}
    channel = pick_channel(consent, customer)                          # asked again now: they may have stopped since approval
    if channel is None:
        recipient.status, recipient.reason = "skipped", "no_consent"
        counts["skipped"] += 1
        return
    language = customer_language(customer, row.default_language)
    template = db.scalar(select(MessageTemplate).where(MessageTemplate.name == template_name(campaign.id, recipient.segment, language, channel), MessageTemplate.channel == channel))
    if template is None:
        recipient.status, recipient.reason = "skipped", "no_template"
        counts["skipped"] += 1
        return
    message = service.send_message(
        db, settings, customer, channel, template, campaign_variables(db, customer, product, campaign, row, language, recipient.segment),
        event_key=f"campaign:{campaign.id}", campaign_id=campaign.id, now=now,
    )
    recipient.message_id = message.id
    if message.status == "skipped":
        recipient.status, recipient.reason = "skipped", message.error
        counts["skipped"] += 1
    else:
        recipient.status = "sent"
        counts["sent"] += 1


def cancel(db: Session, campaign: Campaign) -> int:
    """Stop a campaign: recipients not yet messaged are skipped. Returns how many were stopped."""
    stopped = 0
    for recipient in db.scalars(select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign.id, CampaignRecipient.status == "pending")):
        recipient.status, recipient.reason = "skipped", "campaign_cancelled"
        stopped += 1
    campaign.status = "cancelled"
    return stopped


_DISCOUNT_WORDS = re.compile(r"\d+\s*%|\bdiscount|\bsale\b|\boff\b|\bfree\b|رعایت|مفت|سیل", re.IGNORECASE)


def invents_an_offer(text: str, offer_text: str | None) -> bool:
    """True when a message talks about a discount or freebie the seller never gave (project rule 4)."""
    return bool(_DISCOUNT_WORDS.search(text)) and not (offer_text or "").strip()
