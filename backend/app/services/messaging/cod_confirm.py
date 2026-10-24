"""COD auto-confirmation: ask a cash-on-delivery customer "do you really want this order?" and act on the answer.

THE FLOW
1. A new COD order is created (Quick Order form or Shopify). If the customer agreed to WhatsApp and the seller has an APPROVED
   "cod_confirmation" template, one message goes out through `send_message` (so consent, quiet hours and "never twice" all
   apply). The order gets a `cod_confirmations` row in state "awaiting" with a deadline (COD_CONFIRM_HOURS later).
2. The customer answers YES (or taps a Confirm button) -> "confirmed". NO (or a Cancel button) -> "cancelled": the stock that
   was reserved for the order is given back and the seller sees it on the COD page. Anything else is ignored.
3. Nobody answers by the deadline -> "needs_call": the seller should phone the customer, and Order Risk shows the order one
   level higher with the reason "No reply to the confirmation message" (a plain rule, labelled as such, not the model).

NOTE: a typed reply of exactly "cancel" is also a STOP phrase (see text_rules.py) and STOP always wins: the customer is
switched off. A Cancel BUTTON is not text, so it only cancels the order. Typing NO cancels the order and keeps messaging on.

The seller can always record the result of a phone call by hand ("resolve").
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import Customer, Order
from app.models.cod_confirmation import CodConfirmation
from app.services import inventory, order_status
from app.services.messaging import service
from app.services.messaging.settings_store import get_row

logger = logging.getLogger(__name__)

EVENT = "cod_confirmation"
COD_CONFIRM_HOURS = 12            # how long the customer has to answer before the seller is told to call
ANSWER_WINDOW_DAYS = 3            # a YES/NO is read as an answer to the question only this long after it was asked


def get(db: Session, order_id: int) -> CodConfirmation | None:
    return db.scalar(select(CodConfirmation).where(CodConfirmation.order_id == order_id))


def ask(db: Session, settings: Settings, order: Order, now: datetime | None = None) -> CodConfirmation | None:
    """Ask the customer to confirm a COD order. Returns the confirmation row, or None when nothing was asked
    (not a COD order, already asked, or no approved WhatsApp template / consent / number). Commits nothing."""
    now = now or datetime.now(timezone.utc)
    if order.payment_type != "cod" or get(db, order.id) is not None:
        return None
    customer = db.get(Customer, order.customer_id)
    if customer is None:
        return None
    row = get_row(db)
    language = order_status.customer_language(customer, row.default_language)
    template = order_status.pick_template(db, EVENT, "whatsapp", language, row.default_language)
    if template is None or not template.approved_by_seller:
        return None                                   # opt-in: nothing is sent until the seller approves a template
    values = service.customer_variables(customer, row, template.language, order_status.order_variables(db, order, customer, "confirmed", template.language, None, None))
    message = service.send_message(db, settings, customer, "whatsapp", template, values, event_key=f"order:{order.id}:{EVENT}", event=EVENT, order_id=order.id, now=now)
    if message.status not in ("sent", "queued", "delivered", "read"):
        return None                                   # no consent, no number...: nobody was asked, so nobody is waited for
    confirmation = CodConfirmation(order_id=order.id, state="awaiting", asked_at=now, deadline_at=now + timedelta(hours=COD_CONFIRM_HOURS))
    db.add(confirmation)
    db.flush()
    return confirmation


def _finish(db: Session, confirmation: CodConfirmation, state: str, by: str, now: datetime, reply: str | None = None) -> CodConfirmation:
    confirmation.state, confirmation.resolved_by, confirmation.answered_at = state, by, now
    confirmation.reply_text = (reply or None) and reply[:200]
    if state == "cancelled":
        order = db.get(Order, confirmation.order_id)
        if order is not None:
            inventory.release_order(db, order)         # the goods are for sale again
    db.flush()
    return confirmation


def apply_answer(db: Session, customer_id: int, answer: str, text: str | None, at: datetime) -> CodConfirmation | None:
    """A customer wrote YES or NO. If they have an open COD question, this is the answer. Returns the row, or None when the
    message was about something else (so the caller can treat it as, say, the answer to "may we share your video?")."""
    since = at - timedelta(days=ANSWER_WINDOW_DAYS)
    pending = db.scalar(
        select(CodConfirmation).join(Order, Order.id == CodConfirmation.order_id)
        .where(Order.customer_id == customer_id, CodConfirmation.state.in_(("awaiting", "needs_call")), CodConfirmation.asked_at >= since)
        .order_by(CodConfirmation.asked_at.desc()).limit(1)
    )
    if pending is None or answer not in ("yes", "no"):
        return None
    return _finish(db, pending, "confirmed" if answer == "yes" else "cancelled", "customer", at, text)


def resolve(db: Session, order_id: int, result: str, now: datetime | None = None) -> CodConfirmation:
    """The seller phoned the customer and records the outcome."""
    if result not in ("confirmed", "cancelled"):
        raise ApiError(422, "invalid_result", "The result must be confirmed or cancelled.")
    confirmation = get(db, order_id)
    if confirmation is None:
        order = db.get(Order, order_id)
        if order is None or order.payment_type != "cod":
            raise ApiError(404, "not_cod_order", "This is not a cash-on-delivery order.")
        now = now or datetime.now(timezone.utc)
        confirmation = CodConfirmation(order_id=order_id, state="awaiting", asked_at=now, deadline_at=now)
        db.add(confirmation)
        db.flush()
    return _finish(db, confirmation, result, "seller", now or datetime.now(timezone.utc))


def mark_overdue(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Questions nobody answered in time become "needs_call". Safe to run again and again."""
    now = now or datetime.now(timezone.utc)
    overdue = list(db.scalars(select(CodConfirmation).where(CodConfirmation.state == "awaiting", CodConfirmation.deadline_at <= now).limit(200)))
    for confirmation in overdue:
        confirmation.state = "needs_call"
    db.flush()
    return {"needs_call": len(overdue)}
