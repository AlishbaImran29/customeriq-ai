"""Leads: save them from any source, move them along the pipeline, watch the "not contacted in time" rule, and convert them.

PIPELINE   new -> contacted -> interested -> converted      (any open stage -> lost; lost -> new to reopen)
SOURCES    entered by hand, a website form, a Meta Lead Ad (adapter + test mode), a Click-to-WhatsApp chat
SLA        a lead still "new" after `lead_sla_hours` (default 24) raises ONE alert (a notification and a workflow event)
CONVERT    the lead is linked to a customer (found by phone, then email, or created); the lead keeps its history

A lead is not a customer and is NOT given marketing consent: the person asked us a question, which allows answering it,
not sending promotions. Consent is recorded separately, as for any customer.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import Customer
from app.models.lead import Lead, LeadEvent
from app.models.workflow import Task
from app.services.phone import normalise_pk_phone
from app.services.quick_order import find_customer

logger = logging.getLogger(__name__)

OPEN_STAGES = ("new", "contacted", "interested")
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "new": ("contacted", "interested", "converted", "lost"),
    "contacted": ("interested", "converted", "lost"),
    "interested": ("converted", "lost"),
    "converted": (),
    "lost": ("new",),
}
GRAPH_URL = "https://graph.facebook.com"


def _event(db: Session, lead: Lead, event: str, **detail) -> None:
    db.add(LeadEvent(lead_id=lead.id, event=event, detail=detail))


def _clip(value, limit: int) -> str | None:
    text = " ".join(str(value).split())[:limit] if value is not None else ""
    return text or None


def create_lead(db: Session, *, source: str, name=None, phone=None, email=None, campaign=None, utm_source=None, utm_medium=None, utm_campaign=None,
                product_interest=None, notes=None, external_ref=None) -> tuple[Lead, bool]:
    """Save a lead. Returns (lead, created). The same Meta lead, or an open lead with the same phone, is returned instead of saved twice."""
    number = normalise_pk_phone(str(phone)) if phone else None
    address = _clip(email, 320)
    if address and ("@" not in address or " " in address):
        address = None
    if number is None and address is None:
        raise ApiError(422, "no_contact", "A lead needs a valid Pakistani mobile number or an email address.")
    if external_ref:
        existing = db.scalar(select(Lead).where(Lead.external_ref == external_ref))
        if existing is not None:
            return existing, False
    if number:
        existing = db.scalar(select(Lead).where(Lead.phone_normalised == number, Lead.stage.in_(OPEN_STAGES)).order_by(Lead.id.desc()).limit(1))
        if existing is not None:
            _event(db, existing, "seen_again", source=source)
            return existing, False
    lead = Lead(
        name=_clip(name, 120), phone=_clip(phone, 40), phone_normalised=number, email=address, source=source, campaign=_clip(campaign, 160),
        utm_source=_clip(utm_source, 100), utm_medium=_clip(utm_medium, 100), utm_campaign=_clip(utm_campaign, 160),
        product_interest=_clip(product_interest, 200), notes=_clip(notes, 1000), external_ref=_clip(external_ref, 100), stage="new",
    )
    db.add(lead)
    db.flush()
    _event(db, lead, "created", source=source)
    from app.core.config import get_settings
    from app.services.workflows import engine

    engine.emit(db, get_settings(), "lead_created", {"lead_id": lead.id}, f"lead_created:{lead.id}")
    return lead, True


def move(db: Session, lead: Lead, stage: str, *, lost_reason: str | None = None, follow_up_at: datetime | None = None, now: datetime | None = None) -> Lead:
    if stage not in TRANSITIONS:
        raise ApiError(422, "invalid_stage", "Unknown stage.")
    if stage == lead.stage:
        raise ApiError(409, "same_stage", "The lead is already in that stage.")
    if stage not in TRANSITIONS[lead.stage]:
        raise ApiError(409, "invalid_transition", f"A lead cannot go from {lead.stage} to {stage}.")
    if stage == "converted":
        return convert(db, lead, now=now)
    now = now or datetime.now(timezone.utc)
    previous = lead.stage
    lead.stage = stage
    if stage == "contacted" and lead.contacted_at is None:
        lead.contacted_at = now
    if stage == "lost":
        lead.lost_reason = _clip(lost_reason, 200)
        lead.follow_up_at = None
    elif stage == "new":
        lead.lost_reason, lead.sla_alerted = None, False
    if stage in ("contacted", "interested") and follow_up_at is not None:
        lead.follow_up_at = follow_up_at
        db.add(Task(kind="task", title=f"Follow up with {lead.name or lead.phone or lead.email}", detail=lead.product_interest, due_at=follow_up_at))
    _event(db, lead, "moved", frm=previous, to=stage)
    db.flush()
    return lead


def convert(db: Session, lead: Lead, *, now: datetime | None = None) -> Lead:
    """The lead became a customer: link them (an existing customer with the same phone or email is reused)."""
    if lead.stage == "converted":
        raise ApiError(409, "same_stage", "The lead is already converted.")
    if "converted" not in TRANSITIONS[lead.stage]:
        raise ApiError(409, "invalid_transition", f"A lead cannot go from {lead.stage} to converted.")
    now = now or datetime.now(timezone.utc)
    customer = find_customer(db, lead.phone_normalised) if lead.phone_normalised else None
    if customer is None and lead.email:
        customer = db.scalar(select(Customer).where(Customer.email == lead.email).limit(1))
    created = customer is None
    if customer is None:
        customer = Customer(
            external_id=lead.phone_normalised or lead.email, first_name=(lead.name or "").split(" ")[0] or None, last_name=" ".join((lead.name or "").split(" ")[1:]) or None,
            email=lead.email, phone=lead.phone, phone_normalised=lead.phone_normalised, country="Pakistan" if lead.phone_normalised else None,
        )
        db.add(customer)
        db.flush()
    if not customer.acquisition_source:
        customer.acquisition_source = lead.source.replace("_", " ")
    lead.customer_id, lead.stage, lead.follow_up_at = customer.id, "converted", None
    _event(db, lead, "converted", customer_id=customer.id, new_customer=created)
    db.flush()
    return lead


def overdue(db: Session, settings: Settings, now: datetime) -> list[Lead]:
    cutoff = now - timedelta(hours=settings.lead_sla_hours)
    return list(db.scalars(select(Lead).where(Lead.stage == "new", Lead.sla_alerted.is_(False), Lead.created_at <= cutoff).order_by(Lead.created_at).limit(200)))


def check_sla(db: Session, settings: Settings, now: datetime | None = None) -> dict[str, int]:
    """One alert per lead that nobody contacted in time. Safe to run again and again."""
    now = now or datetime.now(timezone.utc)
    from app.services.workflows import engine

    late = overdue(db, settings, now)
    for lead in late:
        lead.sla_alerted = True
        db.add(Task(kind="notification", title=f"Lead not contacted in {settings.lead_sla_hours} hours: {lead.name or lead.phone or lead.email}", detail=lead.product_interest))
        _event(db, lead, "sla_missed", hours=settings.lead_sla_hours)
        engine.emit(db, settings, "lead_sla_missed", {"lead_id": lead.id}, f"lead_sla:{lead.id}", now)
    db.flush()
    return {"sla_alerts": len(late)}


# --- Meta Lead Ads ---------------------------------------------------------------------------------------------------------


def from_meta_fields(db: Session, leadgen_id: str, field_data: list[dict], *, campaign: str | None = None) -> tuple[Lead, bool]:
    """Turn the answers of a Meta instant form (a list of {name, values}) into a lead. Used by the real webhook AND the test mode."""
    answers = {str(f.get("name", "")).lower(): (f.get("values") or [None])[0] for f in field_data if isinstance(f, dict)}
    name = answers.get("full_name") or " ".join(p for p in (answers.get("first_name"), answers.get("last_name")) if p) or None
    interest = next((v for k, v in answers.items() if k not in ("full_name", "first_name", "last_name", "phone_number", "phone", "email") and v), None)
    return create_lead(db, source="meta_lead_ad", name=name, phone=answers.get("phone_number") or answers.get("phone"), email=answers.get("email"),
                       campaign=campaign, product_interest=interest, external_ref=f"meta:{leadgen_id}")


def fetch_meta_lead(settings: Settings, leadgen_id: str) -> dict:
    """Ask Meta for a lead's answers. Needs META_PAGE_TOKEN. Raises ApiError 503 when it is not set, 502 when Meta does not answer."""
    token = settings.meta_page_token.get_secret_value() if settings.meta_page_token else ""
    if not token.strip():
        raise ApiError(503, "meta_not_configured", "Meta Lead Ads is not connected. Add META_PAGE_TOKEN to the backend settings, or use the test mode.")
    url = f"{GRAPH_URL}/{settings.whatsapp_api_version}/{urllib.parse.quote(leadgen_id)}?access_token={urllib.parse.quote(token)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:                      # noqa: S310 (a Meta address)
            return json.loads(response.read(65536) or b"{}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("Could not fetch a Meta lead: %s", type(exc).__name__)
        raise ApiError(502, "meta_unreachable", "Meta did not answer. The lead will be fetched again when Meta retries.") from exc
