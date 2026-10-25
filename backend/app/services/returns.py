"""Returns, refunds and tickets: the rules.

RETURN   requested -> approved | rejected;  approved -> received -> closed.
         On approval the seller picks the outcome: a REFUND is asked for, a REPLACEMENT order is made, or nothing.
         When the goods are received the seller says whether they go back on the shelf (never automatic: they may be damaged).
REFUND   "requested" is a note to self. "recorded" means the seller paid it back themselves and typed what they used.
         THE APP NEVER MOVES MONEY, so nothing here can refund anyone by itself.
Every step is written to `return_events` (who, what, when) and messages the customer when a template for it is approved.
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import Customer, Order
from app.models.returns import Refund, ReturnEvent, ReturnRequest, Ticket, TicketNote
from app.services import inventory, order_status, supabase_storage
from app.services.messaging import service
from app.services.messaging.settings_store import get_row

logger = logging.getLogger(__name__)

OPEN_RETURN = ("requested", "approved", "received")
MAX_EVIDENCE = 6
MAX_IMAGE_BYTES = supabase_storage.MAX_IMAGE_BYTES
MAX_VIDEO_BYTES = 4 * 1024 * 1024                     # the host accepts request bodies of at most 4.5 MB
ALLOWED = {"image/png": "image", "image/jpeg": "image", "image/webp": "image", "video/mp4": "video"}
TICKET_TRANSITIONS = {"open": ("in_progress", "resolved", "closed"), "in_progress": ("open", "resolved", "closed"), "resolved": ("open", "closed"), "closed": ("open",)}


def _log(db: Session, ret: ReturnRequest, event: str, by: str | None = None, **detail) -> None:
    db.add(ReturnEvent(return_id=ret.id, event=event, by=by, detail=detail))


def _tell(db: Session, settings: Settings, ret: ReturnRequest, event: str, now: datetime) -> int:
    """Message the customer about a decision, if they agreed and the seller approved a template. Returns how many messages."""
    customer, order = db.get(Customer, ret.customer_id), db.get(Order, ret.order_id)
    if customer is None or order is None:
        return 0
    row = get_row(db)
    language = order_status.customer_language(customer, row.default_language)
    sent = 0
    for channel in ("whatsapp", "email"):
        template = order_status.pick_template(db, event, channel, language, row.default_language)
        if template is None:
            continue
        extra = order_status.order_variables(db, order, customer, "returned", template.language, None, None)
        values = service.customer_variables(customer, row, template.language, extra)
        service.send_message(db, settings, customer, channel, template, values, event_key=f"return:{ret.id}:{event}", event=event, order_id=order.id, now=now)
        sent += 1
    return sent


# --- returns ---------------------------------------------------------------------------------------------------------------


def request_return(db: Session, order_id: int, reason: str, by: str | None = None) -> ReturnRequest:
    order = db.get(Order, order_id)
    if order is None:
        raise ApiError(404, "order_not_found", "No such order.")
    if db.scalar(select(ReturnRequest.id).where(ReturnRequest.order_id == order.id, ReturnRequest.status.in_(OPEN_RETURN)).limit(1)) is not None:
        raise ApiError(409, "return_exists", "There is already an open return for this order.")
    ret = ReturnRequest(order_id=order.id, customer_id=order.customer_id, reason=reason.strip()[:300])
    db.add(ret)
    db.flush()
    _log(db, ret, "requested", by, reason=ret.reason)
    from app.core.config import get_settings
    from app.services.workflows import engine

    engine.emit(db, get_settings(), "return_requested", {"order_id": order.id, "customer_id": order.customer_id}, f"return_requested:{ret.id}")
    return ret


def approve(db: Session, settings: Settings, ret: ReturnRequest, resolution: str, *, amount: Decimal | None = None, note: str | None = None, by: str | None = None, now: datetime | None = None) -> ReturnRequest:
    if ret.status != "requested":
        raise ApiError(409, "not_requested", "Only a new request can be approved.")
    if resolution not in ("refund", "replacement", "none"):
        raise ApiError(422, "invalid_resolution", "Choose refund, replacement or nothing.")
    now = now or datetime.now(timezone.utc)
    order = db.get(Order, ret.order_id)
    value = amount if amount is not None else order.order_value
    if resolution == "refund" and (value < 0 or value > order.order_value):
        raise ApiError(422, "invalid_amount", "The refund cannot be more than the order total.")
    ret.status, ret.resolution, ret.decision_note, ret.decided_at = "approved", resolution, (note or None) and note[:300], now
    if resolution == "refund":
        db.add(Refund(return_id=ret.id, order_id=order.id, amount=value, status="requested"))
        _log(db, ret, "refund_requested", by, amount=str(value))
    elif resolution == "replacement":
        replacement = _replacement_order(db, settings, order, now)
        ret.replacement_order_id = replacement.id
        _log(db, ret, "replacement_created", by, order=replacement.external_id)
    _log(db, ret, "approved", by, resolution=resolution)
    _tell(db, settings, ret, "return_approved", now)
    db.flush()
    return ret


def _replacement_order(db: Session, settings: Settings, order: Order, now: datetime) -> Order:
    n = db.query(Order).filter(Order.external_id.like(f"REPL-{order.external_id}-%")).count() + 1
    copy = Order(
        external_id=f"REPL-{order.external_id}-{n}"[:100], customer_id=order.customer_id, order_date=date.today(), order_value=Decimal("0"), channel=order.channel, sales_channel=order.sales_channel,
        payment_type="prepaid", city=order.city, products=order.products, item_count=order.item_count, distinct_products=order.distinct_products, source="replacement",
        note=f"Replacement for {order.external_id}",
    )
    db.add(copy)
    db.flush()
    order_status.record_status(db, settings, copy, "confirmed", source="manual", notify=False, now=now, at=now)       # reserves the stock for it
    return copy


def reject(db: Session, settings: Settings, ret: ReturnRequest, note: str | None, *, by: str | None = None, now: datetime | None = None) -> ReturnRequest:
    if ret.status != "requested":
        raise ApiError(409, "not_requested", "Only a new request can be rejected.")
    now = now or datetime.now(timezone.utc)
    ret.status, ret.decision_note, ret.decided_at = "rejected", (note or None) and note[:300], now
    _log(db, ret, "rejected", by, note=ret.decision_note)
    _tell(db, settings, ret, "return_rejected", now)
    db.flush()
    return ret


def receive(db: Session, ret: ReturnRequest, restock: bool, *, by: str | None = None, now: datetime | None = None) -> ReturnRequest:
    if ret.status != "approved":
        raise ApiError(409, "not_approved", "Only an approved return can be marked received.")
    ret.status, ret.received_at = "received", now or datetime.now(timezone.utc)
    if restock:
        order = db.get(Order, ret.order_id)
        done = inventory.restock_order(db, order, f"Return #{ret.id}")
        ret.restocked = any(e.applied for e in done)
    _log(db, ret, "received", by, restock=restock, restocked=ret.restocked)
    db.flush()
    return ret


def close(db: Session, ret: ReturnRequest, *, by: str | None = None) -> ReturnRequest:
    if ret.status != "received":
        raise ApiError(409, "not_received", "Mark the goods received before closing.")
    open_refund = db.scalar(select(Refund.id).where(Refund.return_id == ret.id, Refund.status == "requested").limit(1))
    if open_refund is not None:
        raise ApiError(409, "refund_pending", "Record the refund (or leave this return open) before closing it.")
    ret.status = "closed"
    _log(db, ret, "closed", by)
    db.flush()
    return ret


# --- refunds (recorded, never executed) ---------------------------------------------------------------------------------------


def record_refund(db: Session, settings: Settings, refund: Refund, method: str, reference: str | None, *, by: str | None = None, now: datetime | None = None) -> Refund:
    """The seller says: I paid this back, this way. The app only remembers it (and tells the customer if a template is approved)."""
    if refund.status == "recorded":
        raise ApiError(409, "already_recorded", "This refund is already recorded.")
    if not method.strip():
        raise ApiError(422, "method_required", "Write how you paid it back (for example JazzCash or bank transfer).")
    now = now or datetime.now(timezone.utc)
    refund.status, refund.method, refund.reference, refund.recorded_at, refund.recorded_by = "recorded", method.strip()[:60], (reference or None) and reference.strip()[:100], now, by
    if refund.return_id:
        ret = db.get(ReturnRequest, refund.return_id)
        _log(db, ret, "refund_recorded", by, amount=str(refund.amount), method=refund.method)
        _tell(db, settings, ret, "refund_recorded", now)
    db.flush()
    return refund


# --- evidence ----------------------------------------------------------------------------------------------------------------------


def check_evidence(content: bytes, mime: str) -> str:
    """"image" or "video", or an ApiError. The first bytes must match the claimed type; sizes are limited."""
    kind = ALLOWED.get(mime)
    if kind is None:
        raise ApiError(415, "file_type", "Use a PNG, JPEG or WebP picture, or an MP4 video.")
    if len(content) > (MAX_IMAGE_BYTES if kind == "image" else MAX_VIDEO_BYTES):
        raise ApiError(413, "too_large", f"The file is too large (pictures up to {MAX_IMAGE_BYTES // 1024 // 1024} MB, videos up to {MAX_VIDEO_BYTES // 1024 // 1024} MB).")
    if kind == "video" and content[4:8] != b"ftyp":
        raise ApiError(422, "not_really_video", "This file is not really an MP4 video.")
    if kind == "image":
        found = supabase_storage.detect_image(content)
        if found is None or found[1] != mime:
            raise ApiError(422, "not_really_image", "This file is not really that kind of picture.")
    return kind


# --- tickets --------------------------------------------------------------------------------------------------------------------------


def move_ticket(ticket: Ticket, status: str, now: datetime | None = None) -> Ticket:
    if status not in TICKET_TRANSITIONS:
        raise ApiError(422, "invalid_status", "Unknown status.")
    if status == ticket.status:
        raise ApiError(409, "same_status", "The ticket already has that status.")
    if status not in TICKET_TRANSITIONS[ticket.status]:
        raise ApiError(409, "invalid_transition", f"A ticket cannot go from {ticket.status} to {status}.")
    ticket.status = status
    ticket.resolved_at = (now or datetime.now(timezone.utc)) if status in ("resolved", "closed") else None
    return ticket


def add_note(db: Session, ticket: Ticket, text: str, author: str | None) -> TicketNote:
    note = TicketNote(ticket_id=ticket.id, author=author, text=text.strip()[:2000])
    db.add(note)
    db.flush()
    return note
