"""Who agreed to be messaged (project rule 1) and who stopped (rule 2).

`customer_consent` holds the current answer per customer and channel; `consent_events` keeps every change.
There is no "default yes": a customer with no row has NOT agreed, and nothing is sent to them.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import ConsentEvent, Customer, CustomerConsent, Message
from app.models.messaging import CHANNELS

SOURCES_MANUAL = {"manual", "import", "add_order", "shopify", "whatsapp_chat"}


def _check_channel(channel: str) -> None:
    if channel not in CHANNELS:
        raise ApiError(422, "invalid_channel", "The channel must be whatsapp or email.")


def get_consent(db: Session, customer_id: int, channel: str) -> CustomerConsent | None:
    return db.scalar(select(CustomerConsent).where(CustomerConsent.customer_id == customer_id, CustomerConsent.channel == channel))


def consent_state(db: Session, customer_id: int, channel: str) -> str:
    """"opted_in", "opted_out" (they stopped or were opted out) or "none" (never recorded)."""
    row = get_consent(db, customer_id, channel)
    if row is None:
        return "none"
    return "opted_in" if row.opted_in else "opted_out"


def set_consent(
    db: Session, customer_id: int, channel: str, opted_in: bool, source: str, *, note: str | None = None, today: date | None = None
) -> CustomerConsent:
    """Record a consent change (and its history entry). Does not commit: the caller decides.

    Asking for the state a customer is already in changes nothing and adds no history entry.
    """
    _check_channel(channel)
    row = get_consent(db, customer_id, channel)
    if row is not None and row.opted_in == opted_in:
        return row
    when = today or date.today()
    if row is None:
        row = CustomerConsent(customer_id=customer_id, channel=channel, opted_in=opted_in, changed_on=when, source=source[:40])
        db.add(row)
    else:
        row.opted_in, row.changed_on, row.source = opted_in, when, source[:40]
    db.add(ConsentEvent(customer_id=customer_id, channel=channel, action="opt_in" if opted_in else "opt_out", source=source[:40], note=(note or None) and note[:200]))
    db.flush()
    if not opted_in:
        cancel_waiting_messages(db, customer_id, channel)
    return row


def cancel_waiting_messages(db: Session, customer_id: int, channel: str) -> int:
    """After an opt-out: messages still waiting in the queue for this customer and channel are cancelled."""
    waiting = db.scalars(select(Message).where(Message.customer_id == customer_id, Message.channel == channel, Message.status == "queued"))
    count = 0
    for message in waiting:
        message.status, message.error = "skipped", "opted_out"
        count += 1
    return count


def consent_counts(db: Session) -> dict[str, dict[str, int]]:
    """How many customers are opted in / out per channel, and how many have never been asked."""
    total = db.scalar(select(func.count()).select_from(Customer)) or 0
    result: dict[str, dict[str, int]] = {}
    for channel in CHANNELS:
        opted_in = db.scalar(select(func.count()).select_from(CustomerConsent).where(CustomerConsent.channel == channel, CustomerConsent.opted_in.is_(True))) or 0
        opted_out = db.scalar(select(func.count()).select_from(CustomerConsent).where(CustomerConsent.channel == channel, CustomerConsent.opted_in.is_(False))) or 0
        result[channel] = {"optedIn": int(opted_in), "optedOut": int(opted_out), "notAsked": int(total - opted_in - opted_out)}
    return result
