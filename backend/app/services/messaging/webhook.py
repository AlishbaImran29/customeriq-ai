"""What the outside world tells us: Meta's WhatsApp webhook and the email unsubscribe link.

SECURITY. The webhook address is public, so anyone could post to it. Meta signs every call with HMAC-SHA256 of the
raw body using the app secret and sends the result in the X-Hub-Signature-256 header. We recompute it and compare
in constant time; a call without a valid signature is refused BEFORE anything is read or changed.

STOP. A reply that is a stop request ("STOP", "band karo", "بند کرو"...) switches that customer's WhatsApp consent
off immediately and cancels any message of theirs that is waiting in the queue (project rule 2).
"""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Customer, IncomingMessage, Message
from app.services.messaging import consent as consent_service
from app.services.messaging.text_rules import is_stop, yes_or_no
from app.services.messaging.tokens import read_unsubscribe_token

logger = logging.getLogger(__name__)

# What a tapped quick-reply button means. Buttons are not typed text, so they are never read as STOP.
BUTTON_ANSWERS = {"confirm": "yes", "yes": "yes", "confirmed": "yes", "cancel": "no", "no": "no", "reject": "no"}

RANK = {"queued": 0, "sent": 1, "delivered": 2, "read": 3, "replied": 4}
REPLY_WINDOW_DAYS = 3                                   # a reply counts as an answer to messages sent in this period


def verify_signature(app_secret: str | None, body: bytes, header: str | None) -> bool:
    """True only for a genuine call from Meta. No secret configured means NOTHING is accepted."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


def verify_challenge(settings: Settings, mode: str | None, token: str | None) -> bool:
    """Meta's one-time check when the webhook is registered: our verify token must match."""
    expected = settings.whatsapp_verify_token.get_secret_value() if settings.whatsapp_verify_token else ""
    return mode == "subscribe" and bool(expected) and bool(token) and hmac.compare_digest(expected, token or "")


def _when(timestamp: str | int | None, fallback: datetime) -> datetime:
    try:
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc) if timestamp is not None else fallback
    except (ValueError, OSError, OverflowError):
        return fallback


def _customer_by_phone(db: Session, digits: str) -> Customer | None:
    return db.scalar(select(Customer).where(Customer.phone_normalised == f"+{digits}").limit(1))


def apply_status(db: Session, provider_id: str, status: str, at: datetime, error_code: str | None = None) -> bool:
    """Move a message along sent -> delivered -> read, never backwards. Returns True when it changed."""
    message = db.scalar(select(Message).where(Message.provider_message_id == provider_id))
    if message is None:
        return False
    if status == "failed":
        if RANK.get(message.status, 0) <= RANK["sent"] and message.status != "failed":
            message.status, message.failed_at, message.error = "failed", at, f"whatsapp_{error_code}" if error_code else "whatsapp_failed"
            return True
        return False
    if status not in ("sent", "delivered", "read") or RANK[status] <= RANK.get(message.status, 0):
        return False
    message.status = status
    setattr(message, {"sent": "sent_at", "delivered": "delivered_at", "read": "read_at"}[status], at)
    if status in ("delivered", "read") and message.delivered_at is None:
        message.delivered_at = at                       # a read implies it was delivered
    return True


def _mark_replied(db: Session, customer_id: int, at: datetime) -> None:
    since = at - timedelta(days=REPLY_WINDOW_DAYS)
    latest = db.scalar(
        select(Message).where(Message.customer_id == customer_id, Message.channel == "whatsapp", Message.status.in_(("sent", "delivered", "read")), Message.sent_at >= since)
        .order_by(Message.sent_at.desc()).limit(1)
    )
    if latest is not None:
        latest.status, latest.replied_at = "replied", at
        if latest.delivered_at is None:
            latest.delivered_at = at


def record_incoming(db: Session, provider_id: str, from_digits: str, kind: str, text: str | None, at: datetime, media_id: str | None = None, mime: str | None = None) -> IncomingMessage | None:
    """Save a customer's message once (a repeated delivery of the same message is ignored) and act on STOP."""
    if db.scalar(select(IncomingMessage.id).where(IncomingMessage.provider_message_id == provider_id)) is not None:
        return None
    customer = _customer_by_phone(db, from_digits)
    stop = kind == "text" and is_stop(text)
    incoming = IncomingMessage(
        customer_id=customer.id if customer else None, channel="whatsapp", from_address=f"+{from_digits}", provider_message_id=provider_id,
        message_type=kind, body=text, media_id=media_id, mime_type=mime, received_at=at, is_stop=stop,
        answer=(yes_or_no(text) if kind == "text" and not stop else BUTTON_ANSWERS.get((text or "").strip().casefold()) if kind == "button" else None),
    )
    db.add(incoming)
    db.flush()
    if customer is not None:
        if stop:
            consent_service.set_consent(db, customer.id, "whatsapp", False, "whatsapp_stop", note="Customer replied STOP")
        _mark_replied(db, customer.id, at)
        from app.services.workflows import hooks

        hooks.message_received(db, customer.id, text, provider_id)
        from app.services.messaging import media                  # imported here: media.py uses the sending code, which uses this file's neighbours

        if kind in ("image", "video"):
            media.queue_media(db, incoming, at)                   # a video after a delivery: to be downloaded and stored
        elif incoming.answer:
            from app.services.messaging import cod_confirm

            # YES / NO first answers an open "confirm your COD order" question; otherwise it answers "may we share your video?"
            if cod_confirm.apply_answer(db, customer.id, incoming.answer, text, at) is None:
                media.apply_share_answer(db, customer.id, incoming.answer, at)
    else:
        logger.info("Incoming WhatsApp message from a number that is not a customer")
    return incoming


def process_whatsapp_payload(db: Session, payload: dict, now: datetime | None = None) -> dict[str, int]:
    """Handle one webhook body. Commits nothing. Unknown shapes are ignored, never an error: Meta must get a 200."""
    now = now or datetime.now(timezone.utc)
    counts = {"statuses": 0, "incoming": 0, "stops": 0}
    for entry in payload.get("entry", []) if isinstance(payload, dict) else []:
        for change in (entry.get("changes", []) if isinstance(entry, dict) else []):
            value = change.get("value", {}) if isinstance(change, dict) else {}
            for status in value.get("statuses", []) or []:
                if not isinstance(status, dict) or not status.get("id"):
                    continue
                errors = status.get("errors") or [{}]
                code = str(errors[0].get("code")) if isinstance(errors[0], dict) and errors[0].get("code") is not None else None
                counts["statuses"] += int(apply_status(db, status["id"], str(status.get("status")), _when(status.get("timestamp"), now), code))
            for message in value.get("messages", []) or []:
                if not isinstance(message, dict) or not message.get("id") or not message.get("from"):
                    continue
                kind = message.get("type") if message.get("type") in ("text", "image", "video", "button", "interactive") else "other"
                media = message.get(kind, {}) if kind in ("image", "video") else {}
                text = (message.get("text") or {}).get("body") if kind == "text" else (media.get("caption") if media else None)
                if kind == "button":                                    # a quick-reply button on a template: its title or payload
                    button = message.get("button") or {}
                    text = button.get("payload") or button.get("text")
                elif kind == "interactive":                             # a button on an interactive message
                    reply = (message.get("interactive") or {}).get("button_reply") or {}
                    kind, text = "button", reply.get("id") or reply.get("title")
                saved = record_incoming(db, message["id"], str(message["from"]), kind, text, _when(message.get("timestamp"), now), media.get("id"), media.get("mime_type"))
                if saved is not None:
                    counts["incoming"] += 1
                    counts["stops"] += int(saved.is_stop)
    return counts


def unsubscribe(db: Session, settings: Settings, token: str) -> bool:
    """Handle a click on an email's unsubscribe link. True when the token was genuine (and the customer is now opted out)."""
    parsed = read_unsubscribe_token(settings, token)
    if parsed is None:
        return False
    customer_id, channel = parsed
    if db.get(Customer, customer_id) is None:
        return True                                       # nothing to change, and nothing to reveal
    consent_service.set_consent(db, customer_id, channel, False, "email_unsubscribe" if channel == "email" else "unsubscribe_link", note="Used the unsubscribe link")
    return True
