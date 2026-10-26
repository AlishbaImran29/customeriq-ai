"""Customer records: erase a customer's personal data, and show one timeline.

ANONYMISE keeps the orders (so revenue and retention figures stay true) but removes everything that points to a person: name,
email, phone, notes, tags, every message and reply, every customer video (file and record) and the consent record. DELETE removes
the customer and, with them, their orders.

The audit line never contains a name, phone or email: only the customer's number in the app and counts.
"""

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import (
    CampaignRecipient, ConsentEvent, Customer, CustomerConsent, CustomerMedia, IncomingMessage, JourneyEnrollment, Message, Order, OrderStatusHistory,
)
from app.models.customer_audit import CustomerAudit
from app.services import supabase_storage

MAX_TAGS = 20
MAX_TAG_LENGTH = 30


def audit(db: Session, action: str, customer: Customer | int, **detail) -> None:
    ref = customer if isinstance(customer, int) else customer.id
    db.add(CustomerAudit(action=action, customer_ref=f"customer:{ref}", detail=detail))


def display_name(c: Customer) -> str:
    return " ".join(p for p in (c.first_name, c.last_name) if p) or c.external_id


def clean_tags(tags: list[str]) -> list[str]:
    seen, out = set(), []
    for tag in tags:
        tag = " ".join(str(tag).split())[:MAX_TAG_LENGTH]
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            out.append(tag)
    return out[:MAX_TAGS]


# --- erase ----------------------------------------------------------------------------------------------------------------


def _delete_videos(db: Session, settings: Settings, customer_id: int) -> int:
    count = 0
    for media in list(db.scalars(select(CustomerMedia).where(CustomerMedia.customer_id == customer_id))):
        if media.storage_path:
            supabase_storage.delete_object(settings, settings.supabase_media_bucket, media.storage_path)
        db.delete(media)
        count += 1
    db.flush()
    return count


def anonymise(db: Session, settings: Settings, customer_id: int) -> Customer:
    """Erase everything that points to the person; keep the orders as anonymous figures. Commits nothing."""
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise ApiError(404, "customer_not_found", "No such customer.")
    if customer.status == "anonymised":
        raise ApiError(409, "already_anonymised", "This customer was already erased.")
    videos = _delete_videos(db, settings, customer.id)
    counts = {"videos": videos}
    for name, model in (("messages", Message), ("replies", IncomingMessage), ("consent_history", ConsentEvent), ("consent", CustomerConsent), ("campaign_rows", CampaignRecipient), ("journey_rows", JourneyEnrollment)):
        counts[name] = db.execute(delete(model).where(model.customer_id == customer.id)).rowcount or 0
    counts["order_notes_cleared"] = db.execute(update(Order).where(Order.customer_id == customer.id, Order.note.is_not(None)).values(note=None)).rowcount or 0
    customer.external_id = f"ANON-{customer.id}"
    customer.first_name = customer.last_name = customer.email = customer.phone = customer.phone_normalised = customer.preferred_language = customer.notes = None
    customer.tags = []
    customer.status, customer.anonymised_at = "anonymised", datetime.now(timezone.utc)
    audit(db, "anonymise", customer, **counts)
    db.flush()
    return customer


def delete_customer(db: Session, settings: Settings, customer_id: int) -> None:
    """Remove the customer and, with them, their orders. Commits nothing."""
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise ApiError(404, "customer_not_found", "No such customer.")
    orders = db.scalar(select(func.count()).select_from(Order).where(Order.customer_id == customer.id)) or 0
    videos = _delete_videos(db, settings, customer.id)
    audit(db, "delete", customer, orders=orders, videos=videos)
    # A plain DELETE: the database removes the orders and everything else that belongs to the customer (ON DELETE CASCADE).
    db.execute(delete(Customer).where(Customer.id == customer.id))
    db.expire_all()


# --- timeline and export ----------------------------------------------------------------------------------------------


@dataclass
class Event:
    at: datetime
    kind: str          # order | status | message | reply | consent
    text: str


def _midnight(day) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def timeline(db: Session, customer: Customer, limit: int = 200) -> list[Event]:
    """Everything that happened with this customer, newest first."""
    events: list[Event] = []
    orders = list(db.scalars(select(Order).where(Order.customer_id == customer.id).order_by(Order.order_date.desc()).limit(limit)))
    for o in orders:
        events.append(Event(_midnight(o.order_date), "order", f"Order {o.external_id}: {o.order_value}" + (f" ({o.products})" if o.products else "")))
    ids = [o.id for o in orders]
    if ids:
        for h in db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id.in_(ids)).order_by(OrderStatusHistory.at.desc()).limit(limit)):
            events.append(Event(h.at, "status", f"Order status: {h.status.replace('_', ' ')}"))
    for m in db.scalars(select(Message).where(Message.customer_id == customer.id).order_by(Message.queued_at.desc()).limit(limit)):
        events.append(Event(m.sent_at or m.queued_at, "message", f"{m.channel} message {m.status}: {m.rendered_text[:80]}"))
    for r in db.scalars(select(IncomingMessage).where(IncomingMessage.customer_id == customer.id).order_by(IncomingMessage.received_at.desc()).limit(limit)):
        events.append(Event(r.received_at, "reply", f"Customer wrote ({r.message_type}): {(r.body or '')[:80]}"))
    for c in db.scalars(select(ConsentEvent).where(ConsentEvent.customer_id == customer.id).order_by(ConsentEvent.at.desc()).limit(limit)):
        events.append(Event(c.at, "consent", f"{c.channel} {'agreed' if c.action == 'opt_in' else 'stopped'} ({c.source})"))
    events.sort(key=lambda e: e.at, reverse=True)
    return events[:limit]


def export_csv(db: Session) -> str:
    """All customers as CSV. Anonymised customers are left out. Cells that start with = + - @ are made safe for spreadsheets."""
    def safe(value) -> str:
        text = "" if value is None else str(value)
        return "'" + text if text[:1] in ("=", "+", "-", "@") else text

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["customer_id", "first_name", "last_name", "email", "phone", "country", "preferred_language", "acquisition_source", "tags", "status"])
    for c in db.scalars(select(Customer).where(Customer.status != "anonymised").order_by(Customer.id)):
        writer.writerow([safe(x) for x in (c.external_id, c.first_name, c.last_name, c.email, c.phone, c.country, c.preferred_language, c.acquisition_source, ", ".join(c.tags or []), c.status)])
    return out.getvalue()
