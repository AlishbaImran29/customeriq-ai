"""The support inbox: what a customer wrote, what kind of message it is, and a reply drafted ONLY from the seller's own records.

NO MAKING THINGS UP. A suggested reply is built from three trusted sources and nothing else: the customer's own orders (status, courier,
tracking number), the stock list (name, price, whether it is in stock) and the FAQ answers the seller typed. If the message is about a
complaint, a return, a refund or a dispute, or if the records do not answer it, NO reply is drafted: the message is marked
"needs a person". Order status is given only for the customer whose phone number sent the message (the chat is already matched to
a customer by phone).

The intent is guessed with plain keyword lists in English and Roman Urdu (below). It is a guess and is labelled one.
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import Customer, IncomingMessage, Message, MessageTemplate, Order, Shipment
from app.models.inbox import Conversation, FaqEntry
from app.models.inventory import StockItem
from app.services import data_rules, inventory, order_status
from app.services.messaging import service
from app.services.messaging.settings_store import get_row

# Checked in this order: the first intent with a match wins, so a refund request is never treated as a plain question.
INTENT_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("dispute", ("chargeback", "consumer court", "legal action", "lawyer", "police", "fir ", "court")),
    ("refund", ("refund", "money back", "paisa wapas", "paise wapas", "paisay wapas", "paise wapis", "رقم واپس", "ریفنڈ")),
    ("complaint", ("complaint", "damaged", "broken", "defective", "wrong item", "fake", "fraud", "scam", "cheat", "worst", "kharab", "kharaab", "toot", "galat", "dhoka", "shikayat", "شکایت", "خراب")),
    ("return", ("return", "exchange", "replace", "wapas karna", "wapis karna", "badalna", "badal do", "واپس کرنا", "تبدیل")),
    ("order_status", ("where is my order", "order status", "tracking", "track my", "kab milega", "kab aayega", "kab ayega", "kab tak", "kahan hai", "kahan tak", "not received", "delivery kab", "parcel kahan", "کب ملے", "کہاں ہے")),
    ("product_question", ("price", "rate", "kitne ka", "kitnay ka", "kitne ki", "available", "in stock", "stock", "size", "colour", "color", "hai kya", "milega", "قیمت", "دستیاب")),
]
ESCALATE = {"dispute", "refund", "complaint", "return"}
STATUS_PHRASE = {
    "confirmed": "confirmed and being prepared", "dispatched": "dispatched", "in_transit": "on its way", "out_for_delivery": "out for delivery today",
    "delivered": "delivered", "returned": "being returned",
}
DIGITS = re.compile(r"\d[\d,\.]*")


def _norm(text: str | None) -> str:
    return " ".join(unicodedata.normalize("NFKC", text or "").casefold().split())


def classify(text: str | None) -> str:
    """"dispute", "refund", "complaint", "return", "order_status", "product_question" or "other". A guess from keywords."""
    t = f" {_norm(text)} "
    for intent, words in INTENT_WORDS:
        if any(w in t for w in words):
            return intent
    return "other"


@dataclass
class Suggestion:
    intent: str
    escalate: bool
    reason: str | None = None                    # why no reply was drafted
    draft: str | None = None
    sources: list[str] = field(default_factory=list)


def _first_name(c: Customer) -> str:
    return (c.first_name or "").strip() or "there"


def _order_answer(db: Session, customer: Customer) -> tuple[str | None, list[str]]:
    order = db.scalar(select(Order).where(Order.customer_id == customer.id).order_by(Order.order_date.desc(), Order.id.desc()).limit(1))
    if order is None:
        return None, []
    current = order_status.latest_status(db, order.id)
    if current is None:
        return None, []
    ship = db.scalar(select(Shipment).where(Shipment.order_id == order.id).order_by(Shipment.id.desc()).limit(1))
    courier = (current.courier or (ship.courier if ship else None))
    tracking = (current.tracking_number or (ship.tracking_number if ship else None))
    parts = [f"Hello {_first_name(customer)}, your order {order_status.order_number(order)} is {STATUS_PHRASE.get(current.status, current.status)}."]
    if courier:
        parts.append(f"Courier: {courier}.")
    if tracking:
        parts.append(f"Tracking number: {tracking}.")
    return " ".join(parts), [f"order {order_status.order_number(order)}"]


def _product_answer(db: Session, customer: Customer, text: str) -> tuple[str | None, list[str]]:
    t = _norm(text)
    found = [i for i in db.scalars(select(StockItem).where(StockItem.status == "active")) if i.name.casefold() in t or i.sku.casefold() in t]
    if not found:
        return None, []
    lines = []
    for item in found[:3]:
        price = f"Rs {float(item.selling_price):,.0f}" if item.selling_price is not None else None
        stock = "in stock" if inventory.available(item) > 0 else "out of stock right now"
        lines.append(f"{item.name}: {price + ', ' if price else ''}{stock}.")
    return f"Hello {_first_name(customer)}, " + " ".join(lines), [f"stock item {i.sku}" for i in found[:3]]


def _faq_answer(db: Session, customer: Customer, text: str) -> tuple[str | None, list[str]]:
    t = f" {_norm(text)} "
    for entry in db.scalars(select(FaqEntry).order_by(FaqEntry.id)):
        words = [w.strip().casefold() for w in entry.keywords.split(",") if w.strip()]
        if any(f" {w} " in t or w in t for w in words):
            return f"Hello {_first_name(customer)}, {entry.answer}", [f"your answer: {entry.title}"]
    return None, []


def suggest(db: Session, customer: Customer, text: str | None) -> Suggestion:
    """A draft reply built from records, or a clear "needs a person". The seller always reads it and presses send."""
    intent = classify(text)
    if intent in ESCALATE:
        return Suggestion(intent, True, reason="This is a complaint, return, refund or dispute. A person should answer it.")
    answer, sources = None, []
    if intent == "order_status":
        answer, sources = _order_answer(db, customer)
    elif intent == "product_question":
        answer, sources = _product_answer(db, customer, text or "")
    if answer is None:
        answer, sources = _faq_answer(db, customer, text or "")           # the seller's own answers can cover any topic
    if answer is None:
        return Suggestion(intent, True, reason="Your records do not answer this, so no reply was drafted.")
    return Suggestion(intent, False, draft=answer, sources=sources)


# --- the inbox ------------------------------------------------------------------------------------------------------------------


def conversation(db: Session, customer_id: int) -> Conversation:
    row = db.scalar(select(Conversation).where(Conversation.customer_id == customer_id))
    if row is None:
        row = Conversation(customer_id=customer_id)
        db.add(row)
        db.flush()
    return row


def mark_read(db: Session, customer_id: int, now: datetime | None = None) -> None:
    conversation(db, customer_id).last_read_at = now or datetime.now(timezone.utc)


def reply(db: Session, settings: Settings, customer: Customer, text: str, *, now: datetime | None = None) -> Message:
    """Send a typed reply on WhatsApp through the normal door (consent, address and the 24-hour rule all apply)."""
    now = now or datetime.now(timezone.utc)
    body = text.strip()
    if not body or len(body) > 1000:
        raise ApiError(422, "invalid_reply", "Write a reply of up to 1000 characters.")
    if "{{" in body:
        raise ApiError(422, "invalid_reply", "The reply cannot contain {{ }}.")
    row = get_row(db)
    if not service.effective_dry_run(settings, row) and not service.has_open_session(db, customer.id, now):
        raise ApiError(409, "session_closed", "The customer wrote more than 24 hours ago, so WhatsApp only allows an approved template now.")
    template = MessageTemplate(name=f"reply_{uuid.uuid4().hex[:12]}", channel="whatsapp", category="utility", language="en", event="manual_reply", body=body, approved_by_seller=True)
    db.add(template)
    db.flush()
    message = service.send_message(db, settings, customer, "whatsapp", template, service.customer_variables(customer, row, "en"), event_key=f"reply:{template.name}", event="manual_reply", now=now)
    return message


def response_minutes(db: Session, now: datetime | None = None, days: int = 30) -> tuple[float | None, int]:
    """(average minutes between a customer's message and our next TYPED reply (automatic messages do not count), number of questions measured). Only when there are enough."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    waits: list[float] = []
    for customer_id in db.scalars(select(IncomingMessage.customer_id).where(IncomingMessage.customer_id.is_not(None), IncomingMessage.received_at >= since).distinct()):
        incoming = list(db.scalars(select(IncomingMessage.received_at).where(IncomingMessage.customer_id == customer_id, IncomingMessage.received_at >= since).order_by(IncomingMessage.received_at)))
        replies = list(db.scalars(
            select(Message.queued_at).join(MessageTemplate, MessageTemplate.id == Message.template_id)
            .where(Message.customer_id == customer_id, MessageTemplate.event == "manual_reply", Message.queued_at >= since).order_by(Message.queued_at)
        ))
        for asked in incoming:
            answered = next((r for r in replies if r > asked), None)
            if answered is not None:
                waits.append((answered - asked).total_seconds() / 60)
    return (sum(waits) / len(waits) if data_rules.enough(len(waits)) else None), len(waits)
