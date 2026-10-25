"""Abandoned carts: remind a shopper who left a Shopify checkout, once or twice, and stop the moment they buy.

THE RULES
- Only a source that sends checkout events can fill this (Shopify "checkouts/create" and "checkouts/update").
- A reminder goes only to a customer we already know AND who agreed to that channel. A shopper we do not know, or who has
  not agreed, is recorded as "no_contact" (the cart still counts in the numbers) and is never messaged.
- Reminder 1 goes `cart_first_minutes` after the shopper's last activity (default 60). Reminder 2 goes `cart_second_hours` after
  reminder 1 (default 24; 0 = no second reminder). That is all: never a third.
- A purchase (an order for the same checkout, or any order by the same customer after the checkout) marks the cart recovered
  and cancels the reminders at once. Reminders are marketing messages, so the weekly cap and quiet hours apply too.
- A cart older than EXPIRE_DAYS is expired and left alone.
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Customer, Order
from app.models.abandoned_cart import AbandonedCart
from app.services import order_status
from app.services.messaging import consent, service
from app.services.messaging.settings_store import get_row
from app.services.phone import normalise_pk_phone
from app.services.quick_order import find_customer

logger = logging.getLogger(__name__)

EXPIRE_DAYS = 7
MAX_REMINDERS = 2
CHANNELS = ("whatsapp", "email")
# A skipped reminder that proves we may not message this person: the cart is parked as "no_contact".
NO_CONTACT_REASONS = {"no_consent", "opted_out", "no_phone", "no_email"}


def _when(value, fallback: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return fallback


def _find_customer(db: Session, payload: dict) -> Customer | None:
    phone = normalise_pk_phone(str(payload.get("phone") or (payload.get("shipping_address") or {}).get("phone") or (payload.get("billing_address") or {}).get("phone") or ""))
    customer = find_customer(db, phone) if phone else None
    email = (payload.get("email") or "").strip().lower()
    if customer is None and email:
        customer = db.scalar(select(Customer).where(Customer.email == email).limit(1))
    return customer


def record_checkout(db: Session, payload: dict, now: datetime | None = None) -> AbandonedCart | None:
    """A Shopify checkout was created or changed. Saves or updates the cart (a change restarts the reminder clock)."""
    now = now or datetime.now(timezone.utc)
    if payload.get("id") is None:
        return None
    checkout_id = str(payload["id"])
    cart = db.scalar(select(AbandonedCart).where(AbandonedCart.checkout_id == checkout_id))
    items = [i for i in payload.get("line_items") or [] if isinstance(i, dict)]
    names = ", ".join(f"{i.get('title')}" + (f" x{i.get('quantity')}" if int(i.get("quantity") or 1) > 1 else "") for i in items if i.get("title")) or None
    try:
        total = Decimal(str(payload.get("total_price") or "0"))
    except InvalidOperation:
        total = Decimal("0")
    customer = _find_customer(db, payload)
    updated = _when(payload.get("updated_at"), now)
    if cart is None:
        cart = AbandonedCart(checkout_id=checkout_id, checkout_updated_at=updated, status="open")
        db.add(cart)
    cart.items, cart.total, cart.currency = (names or cart.items), total, (payload.get("currency") or cart.currency)
    cart.checkout_url = (payload.get("abandoned_checkout_url") or cart.checkout_url or None)
    cart.customer_id = customer.id if customer else cart.customer_id
    if cart.status in ("open", "no_contact") and updated > cart.checkout_updated_at:
        cart.checkout_updated_at = updated                      # the shopper did something: the reminder clock restarts
    if payload.get("completed_at"):
        cart.status, cart.recovered_at = "recovered", cart.recovered_at or now
    elif cart.customer_id is None and cart.status == "open":
        cart.status = "no_contact"                              # a shopper we do not know: never messaged
    db.flush()
    return cart


def mark_recovered(db: Session, order: Order, checkout_id: str | None, now: datetime | None = None) -> int:
    """An order was placed: any open cart for that checkout, or for that customer, is recovered. Returns how many."""
    now = now or datetime.now(timezone.utc)
    query = select(AbandonedCart).where(AbandonedCart.status.in_(("open", "no_contact")))
    carts = []
    if checkout_id:
        carts += list(db.scalars(query.where(AbandonedCart.checkout_id == str(checkout_id))))
    carts += [c for c in db.scalars(query.where(AbandonedCart.customer_id == order.customer_id)) if c not in carts]
    for cart in carts:
        cart.status, cart.recovered_at = "recovered", now
    db.flush()
    return len(carts)


def _due(cart: AbandonedCart, row) -> datetime | None:
    if cart.reminders_sent == 0:
        return cart.checkout_updated_at + timedelta(minutes=row.cart_first_minutes)
    if cart.reminders_sent == 1 and row.cart_second_hours > 0 and cart.last_reminder_at is not None:
        return cart.last_reminder_at + timedelta(hours=row.cart_second_hours)
    return None


def run_due(db: Session, settings: Settings, now: datetime | None = None, limit: int = 100) -> dict[str, int]:
    """One scheduler pass: expire old carts, drop the ones whose customer already bought, send the reminders that are due."""
    now = now or datetime.now(timezone.utc)
    row = get_row(db)
    counts = {"reminders": 0, "recovered": 0, "expired": 0, "no_contact": 0}
    for cart in list(db.scalars(select(AbandonedCart).where(AbandonedCart.status == "open").order_by(AbandonedCart.checkout_updated_at).limit(limit))):
        if cart.checkout_updated_at < now - timedelta(days=EXPIRE_DAYS):
            cart.status = "expired"
            counts["expired"] += 1
            continue
        due = _due(cart, row)
        if due is None or due > now:
            continue
        customer = db.get(Customer, cart.customer_id) if cart.customer_id else None
        if customer is None:
            cart.status = "no_contact"
            counts["no_contact"] += 1
            continue
        bought = db.scalar(select(Order.id).where(Order.customer_id == customer.id, Order.order_date >= cart.checkout_updated_at.date()).limit(1))
        if bought is not None:
            cart.status, cart.recovered_at = "recovered", now
            counts["recovered"] += 1
            continue
        outcome = _remind(db, settings, cart, customer, row, now)
        counts["reminders"] += int(outcome == "sent")
        counts["no_contact"] += int(outcome == "no_contact")
    db.flush()
    return counts


def _remind(db: Session, settings: Settings, cart: AbandonedCart, customer: Customer, row, now: datetime) -> str:
    """Send reminder number reminders_sent+1 on the first channel the customer agreed to that has an approved template."""
    number = cart.reminders_sent + 1
    event = f"cart_reminder_{number}"
    language = order_status.customer_language(customer, row.default_language)
    agreed = [c for c in CHANNELS if consent.consent_state(db, customer.id, c) == "opted_in"]
    if not agreed:
        cart.status = "no_contact"
        return "no_contact"
    for channel in agreed:
        template = order_status.pick_template(db, event, channel, language, row.default_language)
        if template is None or not template.approved_by_seller:
            continue
        values = service.customer_variables(customer, row, template.language, {
            "items": cart.items, "checkout_url": cart.checkout_url, "amount": order_status.money(cart.total) if cart.total else None,
        })
        message = service.send_message(db, settings, customer, channel, template, values, event_key=f"cart:{cart.id}:{number}", event=event, now=now)
        if message.status == "skipped" and message.error in NO_CONTACT_REASONS:
            continue
        cart.reminders_sent, cart.last_reminder_at = number, now
        return "sent"
    return "waiting"                                   # no approved template yet (or no way to reach them): try again at the next pass
