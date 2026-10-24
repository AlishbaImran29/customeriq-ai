"""send(): the ONE door every message goes through.

    send_message(db, settings, customer, channel, template, variables, event_key=...)

The checks run in this order, and the first one that fails stops the message and records WHY (status "skipped"
plus a short code), so the seller can always see what happened and nothing is lost silently:

    1. the same event was already handled?  -> return the earlier message (a message is never sent twice)
    2. template approved by the seller?     -> template_not_approved                 (rule 3)
    3. customer opted in on this channel?   -> no_consent / opted_out                (rules 1 and 2)
    4. has an address?                      -> no_phone / no_email
    5. every {{variable}} has a value?      -> missing_variable:<name>               (rule 4: nothing invented)
    6. WhatsApp: allowed by Meta's rules?   -> meta_template_not_approved
    7. marketing: under the weekly cap?     -> weekly_cap
    8. quiet hours?                         -> kept in the queue until the window opens (status "queued")
    9. send through the adapter; a temporary failure is retried later, at most MAX_ATTEMPTS times in total.

`process_queue` is what runs the messages that were waiting (quiet hours, or a retry).
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Customer, IncomingMessage, Message, MessageTemplate, MessagingSettings
from app.services.messaging import consent as consent_service
from app.services.messaging import policy
from app.services.messaging.adapters import Outbound, adapter_for
from app.services.messaging.render import MissingVariable, render, variables_in
from app.services.messaging.settings_store import effective_dry_run, get_row
from app.services.messaging.tokens import unsubscribe_link

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3                                   # in total, the first try included
BACKOFF_MINUTES = (5, 30)                          # the wait after the 1st and the 2nd failed try
SESSION_HOURS = 24                                 # free text is allowed this long after the customer's own message
FALLBACK_NAME = {"en": "customer", "ur": "کسٹمر"}
FALLBACK_STORE = {"en": "our shop", "ur": "ہماری دکان"}
COUNTED_STATUSES = ("queued", "sent", "delivered", "read", "replied")      # what counts towards the weekly cap


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def customer_variables(customer: Customer, row: MessagingSettings, language: str, extra: dict[str, str | None] | None = None) -> dict[str, str | None]:
    """The values every message can use about the customer and the shop. `extra` adds the event's own values
    (order number, amount...). A name that is missing is replaced by a plain word, never made up."""
    values: dict[str, str | None] = {
        "first_name": (customer.first_name or "").strip() or FALLBACK_NAME[language],
        "last_name": (customer.last_name or "").strip() or None,
        "store_name": (row.store_name or "").strip() or FALLBACK_STORE[language],
        "review_link": (row.review_url or "").strip() or None,
    }
    values.update(extra or {})
    return values


def _address(customer: Customer, channel: str) -> str | None:
    """Where to send. An email ending in @example.com is a placeholder (the public demo data uses them), never a real
    inbox, so it counts as "no email" instead of being tried."""
    if channel == "whatsapp":
        phone = customer.phone_normalised or ""
        return phone.lstrip("+") if phone else None
    email = (customer.email or "").strip()
    return email if "@" in email and "placeholder" not in email.lower() and not email.lower().endswith("@example.com") else None


def _skip(message: Message, code: str) -> Message:
    message.status, message.error, message.next_attempt_at = "skipped", code, None
    return message


def has_open_session(db: Session, customer_id: int, now: datetime) -> bool:
    """Did this customer message us on WhatsApp in the last 24 hours? Then Meta allows free text."""
    since = now - timedelta(hours=SESSION_HOURS)
    return db.scalar(select(func.count()).select_from(IncomingMessage).where(IncomingMessage.customer_id == customer_id, IncomingMessage.received_at >= since)) not in (None, 0)


def marketing_count_last_week(db: Session, customer_id: int, now: datetime, exclude_id: int | None = None) -> int:
    since = now - timedelta(days=policy.CAP_WINDOW_DAYS)
    query = select(func.count()).select_from(Message).where(
        Message.customer_id == customer_id, Message.category == "marketing", Message.status.in_(COUNTED_STATUSES), Message.queued_at >= since,
    )
    if exclude_id is not None:
        query = query.where(Message.id != exclude_id)
    return int(db.scalar(query) or 0)


def send_message(
    db: Session, settings: Settings, customer: Customer, channel: str, template: MessageTemplate, variables: dict[str, str | None],
    *, event_key: str, event: str | None = None, campaign_id: int | None = None, journey_id: int | None = None,
    order_id: int | None = None, now: datetime | None = None, not_before: datetime | None = None,
) -> Message:
    """Send (or decide not to send) one message. Always returns the Message record. Commits nothing: the caller does."""
    now = now or now_utc()
    key = f"{customer.id}:{channel}:{event_key}"[:160]
    earlier = db.scalar(select(Message).where(Message.idempotency_key == key))
    if earlier is not None:
        return earlier                                                       # 1. never twice

    message = Message(
        customer_id=customer.id, channel=channel, template_id=template.id, category=template.category,
        idempotency_key=key, rendered_text="", variables=None, status="queued", campaign_id=campaign_id, journey_id=journey_id,
        order_id=order_id, queued_at=now,
    )
    try:
        with db.begin_nested():                                              # a SAVEPOINT: a clash with a parallel request is caught here
            db.add(message)
            db.flush()
    except IntegrityError:
        existing = db.scalar(select(Message).where(Message.idempotency_key == key))
        if existing is not None:
            return existing
        raise

    row = get_row(db)
    dry = effective_dry_run(settings, row)
    message.dry_run = dry
    event = event or template.event

    if not template.approved_by_seller:
        return _skip(message, "template_not_approved")                       # 2.
    state = consent_service.consent_state(db, customer.id, channel)
    if state != "opted_in":
        return _skip(message, "opted_out" if state == "opted_out" else "no_consent")      # 3.
    address = _address(customer, channel)
    if address is None:
        return _skip(message, "no_phone" if channel == "whatsapp" else "no_email")        # 4.

    try:                                                                     # 5.
        text = render(template.body, variables)
        subject = render(template.subject, variables) if template.subject else None
    except MissingVariable as missing:
        return _skip(message, f"missing_variable:{missing.name}"[:200])
    message.rendered_text, message.subject = text, subject
    message.variables = {name: variables.get(name) for name in variables_in(template.body)}

    if channel == "whatsapp" and not dry and not has_open_session(db, customer.id, now):     # 6.
        if not template.meta_template_name or template.meta_approval_status != "approved":
            return _skip(message, "meta_template_not_approved")
    if channel == "email" and template.category == "marketing" and not dry and not unsubscribe_link(settings, customer.id):
        return _skip(message, "no_unsubscribe_link")                         # a marketing email must carry a working unsubscribe link

    if template.category == "marketing" and not policy.cap_allows(marketing_count_last_week(db, customer.id, now, message.id), row.weekly_marketing_cap):
        return _skip(message, "weekly_cap")                                  # 7.

    # `not_before` delays a message on purpose (for example: ask about unboxing 2 hours after delivery).
    when = policy.next_allowed(max(now, not_before or now), row.timezone, row.quiet_start, row.quiet_end, event)
    if when > now:                                                           # 8.
        message.status, message.next_attempt_at = "queued", when
        return message
    return _deliver(db, settings, message, customer, template, row, dry, now)    # 9.


def _outbound(db: Session, settings: Settings, message: Message, customer: Customer, template: MessageTemplate, now: datetime) -> Outbound | None:
    address = _address(customer, message.channel)
    if address is None:
        return None
    if message.channel == "whatsapp":
        use_template = bool(template.meta_template_name) and template.meta_approval_status == "approved" and not has_open_session(db, customer.id, now)
        values = [(message.variables or {}).get(name) or "-" for name in variables_in(template.body)]        # Meta rejects an empty value
        return Outbound("whatsapp", address, message.rendered_text, template.language,
                        meta_template_name=template.meta_template_name if use_template else None, template_values=values if use_template else [])
    return Outbound("email", address, message.rendered_text, template.language, subject=message.subject,
                    unsubscribe_url=unsubscribe_link(settings, customer.id))


def _deliver(
    db: Session, settings: Settings, message: Message, customer: Customer, template: MessageTemplate, row: MessagingSettings, dry: bool, now: datetime
) -> Message:
    out = _outbound(db, settings, message, customer, template, now)
    if out is None:
        return _skip(message, "no_phone" if message.channel == "whatsapp" else "no_email")
    result = adapter_for(message.channel, settings, dry).send(out)
    message.attempts += 1
    message.dry_run = dry
    if result.ok:
        message.status, message.sent_at, message.provider_message_id, message.error, message.next_attempt_at = "sent", now, result.provider_id, None, None
    elif result.transient and message.attempts < MAX_ATTEMPTS:
        wait = BACKOFF_MINUTES[min(message.attempts, len(BACKOFF_MINUTES)) - 1]
        message.status, message.error, message.next_attempt_at = "queued", result.error, now + timedelta(minutes=wait)
    else:
        message.status, message.failed_at, message.error, message.next_attempt_at = "failed", now, result.error, None
    return message


def process_queue(db: Session, settings: Settings, now: datetime | None = None, limit: int = 100) -> dict[str, int]:
    """Run the messages that were waiting: held back by quiet hours, or due for a retry. Commits nothing."""
    now = now or now_utc()
    counts = {"processed": 0, "sent": 0, "requeued": 0, "failed": 0, "skipped": 0}
    due = db.scalars(
        select(Message).where(Message.status == "queued", Message.next_attempt_at.is_not(None), Message.next_attempt_at <= now)
        .order_by(Message.next_attempt_at, Message.id).limit(limit)
    ).all()
    row = get_row(db)
    dry = effective_dry_run(settings, row)
    for message in due:
        counts["processed"] += 1
        customer, template = db.get(Customer, message.customer_id), (db.get(MessageTemplate, message.template_id) if message.template_id else None)
        if customer is None or template is None:
            _skip(message, "template_removed" if template is None else "customer_removed")
        elif consent_service.consent_state(db, customer.id, message.channel) != "opted_in":
            _skip(message, "opted_out")                                       # they may have stopped while it waited
        elif not template.approved_by_seller:
            _skip(message, "template_not_approved")
        else:
            event = template.event
            when = policy.next_allowed(now, row.timezone, row.quiet_start, row.quiet_end, event)
            if when > now:
                message.next_attempt_at = when                                # still quiet hours: wait again
                counts["requeued"] += 1
                continue
            if message.channel == "whatsapp" and not dry and not has_open_session(db, customer.id, now) and (not template.meta_template_name or template.meta_approval_status != "approved"):
                _skip(message, "meta_template_not_approved")
            else:
                _deliver(db, settings, message, customer, template, row, dry, now)
        counts[{"sent": "sent", "queued": "requeued", "failed": "failed", "skipped": "skipped"}.get(message.status, "sent")] += 1
    logger.info("Message queue: %s", counts)
    return counts
