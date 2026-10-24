"""Shopify webhooks: a new order, and a parcel moving.

SECURITY. Shopify signs every call: the header X-Shopify-Hmac-Sha256 is the base64 of HMAC-SHA256 of the RAW body,
made with the app's secret. We recompute it and compare in constant time before reading anything. A shop domain
can be pinned too (SHOPIFY_SHOP_DOMAIN), so only the seller's own shop is accepted.

WHAT HAPPENS
- orders/create: the customer is found (by phone, then email) or created, the order is saved once, and the status
  "confirmed" is recorded (which sends the confirmation if the customer agreed to be messaged). A customer's
  marketing tick-box at Shopify checkout counts as EMAIL consent, but only for a customer we have no answer from
  yet: it never overrides a customer who already opted out.
- fulfillments/create and fulfillments/update: dispatched / in transit / out for delivery / delivered, with the
  courier and tracking number Shopify gives.
- every other topic is accepted and ignored (Shopify must always get a 200 for a call it signed correctly).
"""

import base64
import hashlib
import hmac
import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Customer, Order, WebhookEvent
from app.services import order_status
from app.services.messaging import consent as consent_service
from app.services.phone import normalise_pk_phone
from app.services.quick_order import find_customer

logger = logging.getLogger(__name__)

# Shopify's own words for a parcel's state -> ours. Anything else (label printed, attempted delivery...) is not announced.
SHIPMENT_STATUS = {"confirmed": "dispatched", "in_transit": "in_transit", "out_for_delivery": "out_for_delivery", "delivered": "delivered"}


def verify_hmac(secret: str | None, body: bytes, header: str | None) -> bool:
    if not secret or not header:
        return False
    expected = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(expected, header.strip())


def shop_allowed(settings: Settings, domain: str | None) -> bool:
    pinned = (settings.shopify_shop_domain or "").strip().lower()
    return not pinned or (domain or "").strip().lower() == pinned


def already_handled(db: Session, event_id: str | None) -> bool:
    """True when this webhook call was handled before (Shopify retries). Records it otherwise."""
    if not event_id:
        return False
    try:
        with db.begin_nested():
            db.add(WebhookEvent(source="shopify", event_id=event_id[:120]))
            db.flush()
    except IntegrityError:
        return True
    return False


def _date(text: str | None) -> date:
    try:
        return datetime.fromisoformat((text or "").replace("Z", "+00:00")).date()
    except ValueError:
        return date.today()


def _phone(payload: dict) -> str | None:
    for source in (payload, payload.get("customer") or {}, payload.get("shipping_address") or {}, payload.get("billing_address") or {}):
        number = normalise_pk_phone(str(source.get("phone") or "")) if isinstance(source, dict) else None
        if number:
            return number
    return None


def find_or_create_customer(db: Session, payload: dict) -> Customer:
    shopify_customer = payload.get("customer") if isinstance(payload.get("customer"), dict) else {}
    phone = _phone(payload)
    email = (payload.get("email") or shopify_customer.get("email") or "").strip().lower() or None
    customer = find_customer(db, phone) if phone else None
    if customer is None and email:
        customer = db.scalar(select(Customer).where(Customer.email == email).limit(1))
    if customer is None:
        shipping = payload.get("shipping_address") or {}
        key = f"SHOPIFY-C{shopify_customer['id']}" if shopify_customer.get("id") else (phone or email or f"SHOPIFY-O{payload.get('id')}")
        customer = Customer(
            external_id=key[:100], first_name=(shopify_customer.get("first_name") or shipping.get("first_name") or None),
            last_name=(shopify_customer.get("last_name") or shipping.get("last_name") or None), email=email, phone=phone,
            phone_normalised=phone, country=(shipping.get("country") or "Pakistan")[:100],
        )
        db.add(customer)
        db.flush()
    else:
        customer.phone_normalised = customer.phone_normalised or phone
        customer.email = customer.email or email
    ticked = bool(shopify_customer.get("accepts_marketing")) or (shopify_customer.get("email_marketing_consent") or {}).get("state") == "subscribed"
    if ticked and email and consent_service.consent_state(db, customer.id, "email") == "none":
        consent_service.set_consent(db, customer.id, "email", True, "shopify", note="Ticked the marketing box at checkout")
    return customer


def upsert_order(db: Session, payload: dict) -> Order | None:
    if payload.get("id") is None:
        return None
    # The order is saved under Shopify's own id (a fulfillment call names the order by that id). The number the
    # customer knows ("#1001") goes into the note, and order_status.order_number() reads it back from there.
    external_id = f"SHOPIFY-{payload['id']}"
    existing = db.scalar(select(Order).where(Order.external_id == external_id))
    if existing is not None:
        return existing
    customer = find_or_create_customer(db, payload)
    try:
        value = Decimal(str(payload.get("total_price") or "0"))
    except InvalidOperation:
        value = Decimal("0")
    items = [i for i in payload.get("line_items") or [] if isinstance(i, dict)]
    gateways = " ".join(str(g) for g in payload.get("payment_gateway_names") or []).lower()
    order = Order(
        external_id=external_id, customer_id=customer.id, order_date=_date(payload.get("created_at")), order_value=max(value, Decimal("0")),
        channel="Shopify", sales_channel="website", payment_type="cod" if ("cod" in gateways or "cash on delivery" in gateways) else "prepaid",
        city=((payload.get("shipping_address") or {}).get("city") or None), products=", ".join(str(i.get("title") or "").strip() for i in items if i.get("title")) or None,
        item_count=sum(int(i.get("quantity") or 1) for i in items) or None, distinct_products=len(items) or None, source="shopify",
        note=f"Shopify order {payload.get('name') or '#' + str(payload.get('order_number') or payload['id'])}"[:200],
    )
    db.add(order)
    db.flush()
    return order


def handle(db: Session, settings: Settings, topic: str, payload: dict, now: datetime | None = None) -> dict:
    """Apply one verified Shopify call. Commits nothing. Returns a small summary."""
    now = now or datetime.now(timezone.utc)
    if topic == "orders/create":
        order = upsert_order(db, payload)
        if order is None:
            return {"ignored": "no order number"}
        change = order_status.record_status(db, settings, order, "confirmed", at=now, source="shopify", now=now)
        from app.services.messaging import cod_confirm

        cod_confirm.ask(db, settings, order, now)
        return {"order": order.external_id, "recorded": change.recorded, "messages": [m.status for m in change.messages]}
    if topic in ("fulfillments/create", "fulfillments/update"):
        order = db.scalar(select(Order).where(Order.external_id == f"SHOPIFY-{payload.get('order_id')}"))
        if order is None:
            return {"ignored": "unknown order"}
        status = SHIPMENT_STATUS.get(str(payload.get("shipment_status") or ""), "dispatched" if topic == "fulfillments/create" and not payload.get("shipment_status") else None)
        if status is None:
            return {"ignored": f"shipment_status {payload.get('shipment_status')}"}
        tracking = payload.get("tracking_number") or next(iter(payload.get("tracking_numbers") or []), None)
        change = order_status.record_status(db, settings, order, status, at=now, source="shopify", courier=payload.get("tracking_company"), tracking=tracking, now=now)
        return {"order": order.external_id, "status": status, "recorded": change.recorded, "messages": [m.status for m in change.messages]}
    if topic == "products/create":
        return _new_product(db, payload)
    return {"ignored": topic}


def _new_product(db: Session, payload: dict) -> dict:
    """A product added in Shopify: save it, and make its DRAFT announcement campaign (nothing is sent)."""
    import re

    from app.services.messaging import campaigns

    if payload.get("id") is None or not payload.get("title"):
        return {"ignored": "no product id or title"}
    variants = [v for v in payload.get("variants") or [] if isinstance(v, dict)]
    try:
        price = Decimal(str(variants[0].get("price"))) if variants and variants[0].get("price") is not None else None
    except InvalidOperation:
        price = None
    text = re.sub(r"<[^>]+>", " ", str(payload.get("body_html") or ""))
    description = " ".join(text.split())[:1500] or None
    product, campaign = campaigns.create_product(
        db, name=str(payload["title"]), category=payload.get("product_type") or None, price=price, description=description,
        source="shopify", external_id=str(payload["id"]),
    )
    return {"product": product.name, "campaign": campaign.id, "status": campaign.status}

