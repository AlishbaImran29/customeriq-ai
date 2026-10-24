"""Order status (Auto Messenger part 2): keep the history of each order's status and tell the customer.

    record_status(db, settings, order, "dispatched", at=..., source="manual", courier=..., tracking=...)

Where a status comes from: a Shopify webhook, a courier status file, the manual "change status" button, or an order
added by hand (which starts at "confirmed").

WHEN A CUSTOMER IS MESSAGED
- only when the status moves FORWARD (confirmed < dispatched < in_transit < out_for_delivery < delivered; "returned"
  can follow any of them). Setting the same status again, or going back, is recorded but never messages anyone.
- only when the event is FRESH (at most NOTIFY_MAX_AGE_DAYS old). Importing last year's courier file must not text
  hundreds of customers about old parcels.
- through the one door, `send_message`, so consent, approval, quiet hours and "never twice" all apply. The event key
  is "order:<id>:<status>", so each status of each order is announced at most once per channel.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import Customer, Message, MessageTemplate, Order, OrderStatusHistory, Shipment
from app.models.order_status import ORDER_STATUSES, STATUS_SOURCES
from app.services import inventory
from app.services.messaging import service
from app.services.messaging.settings_store import get_row

logger = logging.getLogger(__name__)

RANK = {"confirmed": 1, "dispatched": 2, "in_transit": 3, "out_for_delivery": 4, "delivered": 5, "returned": 6}
NOTIFY_MAX_AGE_DAYS = 3                  # a status older than this is recorded but not announced
HISTORY_MAX_AGE_DAYS = 30                # a courier file's old statuses are not even recorded (keeps the table small)
COD_STATUSES = {"confirmed", "dispatched", "in_transit", "out_for_delivery"}      # while the cash is still to be handed over
CHANNELS = ("whatsapp", "email")


def event_name(status: str) -> str:
    return f"order_{status}"


def is_forward(previous: str | None, new: str) -> bool:
    """Does moving from `previous` to `new` count as progress? (The first status always does.)"""
    if previous is None:
        return True
    if previous == "returned":
        return False
    if new == "returned":
        return True
    return RANK[new] > RANK[previous]


def latest_status(db: Session, order_id: int) -> OrderStatusHistory | None:
    return db.scalar(select(OrderStatusHistory).where(OrderStatusHistory.order_id == order_id).order_by(OrderStatusHistory.at.desc(), OrderStatusHistory.id.desc()).limit(1))


def order_number(order: Order) -> str:
    """The number the customer knows: a Shopify order shows as the shop's own "#1001" (kept in the note), others as they are."""
    if order.external_id.startswith("SHOPIFY-"):
        match = re.match(r"Shopify order (\S+)", order.note or "")
        return match.group(1) if match else order.external_id
    return order.external_id


def money(amount) -> str:
    return f"Rs {float(amount):,.0f}"


def order_variables(db: Session, order: Order, customer: Customer, status: str, language: str, courier: str | None, tracking: str | None) -> dict[str, str | None]:
    """The values an order message can use. Anything unknown stays empty, so nothing is invented."""
    shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.id).order_by(Shipment.id.desc()).limit(1))
    courier = courier or (shipment.courier if shipment else None)
    tracking = tracking or (shipment.tracking_number if shipment else None)
    parts_en = ", ".join(p for p in (f"Courier: {courier}" if courier else "", f"tracking number: {tracking}" if tracking else "") if p)
    parts_ur = "، ".join(p for p in (f"کورئیر: {courier}" if courier else "", f"ٹریکنگ نمبر: {tracking}" if tracking else "") if p)
    cod = order.payment_type == "cod" and status in COD_STATUSES
    return {
        "order_number": order_number(order), "items": order.products, "amount": money(order.order_value),
        "courier": courier, "tracking_number": tracking,
        "tracking_line": (parts_en + "." if parts_en else None) if language == "en" else (parts_ur + "۔" if parts_ur else None),
        "cod_note": (f"Please keep {money(order.order_value)} ready." if language == "en" else f"براہ کرم {money(order.order_value)} تیار رکھیں۔") if cod else None,
    }


def pick_template(db: Session, event: str, channel: str, language: str, fallback_language: str) -> MessageTemplate | None:
    """The template for an event: the customer's language first, then the shop's default; an approved one before an unapproved."""
    candidates = list(db.scalars(select(MessageTemplate).where(MessageTemplate.event == event, MessageTemplate.channel == channel)))
    if not candidates:
        return None

    def rank(t: MessageTemplate) -> tuple[int, int]:
        return (0 if t.approved_by_seller else 1, 0 if t.language == language else 1 if t.language == fallback_language else 2)

    return sorted(candidates, key=rank)[0]


def customer_language(customer: Customer, default: str) -> str:
    return customer.preferred_language if customer.preferred_language in ("ur", "en") else default


@dataclass
class StatusChange:
    recorded: bool                                  # a history row was added
    announced: bool                                 # the move counted as news for the customer
    history: OrderStatusHistory | None = None
    messages: list[Message] = field(default_factory=list)
    reason: str | None = None                       # why nothing was announced: same_status, not_forward, too_old, not_requested


def record_status(
    db: Session, settings: Settings, order: Order, status: str, *, at: datetime | None = None, source: str,
    courier: str | None = None, tracking: str | None = None, note: str | None = None, notify: bool = True, now: datetime | None = None,
) -> StatusChange:
    """Record a status and, if it is news and fresh, message the customer. Commits nothing."""
    if status not in ORDER_STATUSES:
        raise ApiError(422, "invalid_status", "The status must be one of: " + ", ".join(ORDER_STATUSES) + ".")
    if source not in STATUS_SOURCES:
        raise ValueError(f"unknown source {source}")
    now = now or datetime.now(timezone.utc)
    at = at or now
    current = latest_status(db, order.id)
    if current is not None and current.status == status:
        # Nothing new, but remember a courier or tracking number that arrived later.
        if courier and not current.courier:
            current.courier = courier[:60]
        if tracking and not current.tracking_number:
            current.tracking_number = tracking[:80]
        return StatusChange(False, False, current, reason="same_status")

    forward = is_forward(current.status if current else None, status)
    history = OrderStatusHistory(order_id=order.id, status=status, at=at, source=source, courier=(courier or None) and courier[:60],
                                 tracking_number=(tracking or None) and tracking[:80], note=(note or None) and note[:200])
    db.add(history)
    db.flush()
    if at >= now - timedelta(days=NOTIFY_MAX_AGE_DAYS):
        inventory.on_status(db, order, status)        # reserve on confirmed, sell on dispatched (fresh statuses only)
    if not notify:
        return StatusChange(True, False, history, reason="not_requested")
    if not forward:
        return StatusChange(True, False, history, reason="not_forward")
    if at < now - timedelta(days=NOTIFY_MAX_AGE_DAYS):
        return StatusChange(True, False, history, reason="too_old")
    return StatusChange(True, True, history, messages=_notify(db, settings, order, status, courier, tracking, now))


def _notify(db: Session, settings: Settings, order: Order, status: str, courier: str | None, tracking: str | None, now: datetime) -> list[Message]:
    customer = db.get(Customer, order.customer_id)
    if customer is None:
        return []
    row = get_row(db)
    language = customer_language(customer, row.default_language)
    event = event_name(status)
    messages = []
    for channel in CHANNELS:
        template = pick_template(db, event, channel, language, row.default_language)
        if template is None:
            logger.info("No %s template for %s: nothing was sent", channel, event)
            continue
        values = service.customer_variables(customer, row, template.language, order_variables(db, order, customer, status, template.language, courier, tracking))
        messages.append(service.send_message(
            db, settings, customer, channel, template, values, event_key=f"order:{order.id}:{status}", event=event, order_id=order.id, now=now,
        ))
    if status == "delivered":
        messages.extend(_ask_for_unboxing(db, settings, order, customer, row, courier, tracking, now))
    return messages


UNBOXING_DELAY_HOURS = 2                 # give the customer time to open the parcel before asking for a video


def _ask_for_unboxing(db: Session, settings: Settings, order: Order, customer: Customer, row, courier: str | None, tracking: str | None, now: datetime) -> list[Message]:
    """After a delivery: "did it arrive? send us an unboxing video" on WhatsApp (a video cannot be sent by email)."""
    template = pick_template(db, "delivered_unboxing", "whatsapp", customer_language(customer, row.default_language), row.default_language)
    if template is None:
        return []
    values = service.customer_variables(customer, row, template.language, order_variables(db, order, customer, "delivered", template.language, courier, tracking))
    return [service.send_message(
        db, settings, customer, "whatsapp", template, values, event_key=f"order:{order.id}:delivered_unboxing", event="delivered_unboxing",
        order_id=order.id, now=now, not_before=now + timedelta(hours=UNBOXING_DELAY_HOURS),
    )]


def record_from_shipment(db: Session, settings: Settings, order: Order, shipment_status: str, event_date, courier: str | None, tracking: str | None) -> None:
    """A courier file said where a parcel is. delivered / returned / in transit become order statuses; "lost" does not.

    The event is dated by the file (noon UTC of that day). A status older than HISTORY_MAX_AGE_DAYS is not even
    recorded, and one older than NOTIFY_MAX_AGE_DAYS is recorded without messaging anyone."""
    status = {"delivered": "delivered", "returned": "returned", "in_transit": "in_transit"}.get(shipment_status)
    if status is None:
        return
    at = datetime(event_date.year, event_date.month, event_date.day, 12, 0, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if at < now - timedelta(days=HISTORY_MAX_AGE_DAYS):
        return
    record_status(db, settings, order, status, at=min(at, now), source="courier_import", courier=courier, tracking=tracking, now=now)
