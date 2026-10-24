"""Gather the facts a workflow's conditions ask about, from the ids an event carries.

An event carries only ids (order_id, customer_id, item_id, text). Facts are looked up here, and only the ones the workflow's
conditions actually use are computed (the customer's segment is the expensive one, so it is asked for only when needed).
All values are plain numbers, text, booleans or lists, so they can be saved with the run as the record of what was seen.
"""

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Customer, Order, OrderStatusHistory
from app.models.inventory import StockItem
from app.services import inventory
from app.services.messaging import consent


def _latest_status(db: Session, order_id: int) -> str | None:
    return db.scalar(select(OrderStatusHistory.status).where(OrderStatusHistory.order_id == order_id).order_by(OrderStatusHistory.at.desc(), OrderStatusHistory.id.desc()).limit(1))


def build(db: Session, payload: dict[str, Any], needed: set[str], today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    facts: dict[str, Any] = {}
    order = db.get(Order, payload["order_id"]) if payload.get("order_id") else None
    customer_id = payload.get("customer_id") or (order.customer_id if order else None)
    customer = db.get(Customer, customer_id) if customer_id else None

    if order is not None:
        facts.update(
            order_total=float(order.order_value), order_payment_type=order.payment_type, order_city=order.city,
            order_status=payload.get("status") or _latest_status(db, order.id),
        )
    if customer is not None:
        if needed & {"customer_orders", "customer_total_spent", "customer_days_since_last_order"}:
            count, spent, last = db.execute(
                select(func.count(Order.id), func.coalesce(func.sum(Order.order_value), 0), func.max(Order.order_date)).where(Order.customer_id == customer.id)
            ).one()
            facts.update(customer_orders=int(count), customer_total_spent=float(spent), customer_days_since_last_order=(today - last).days if last else None)
        facts["customer_tags"] = list(customer.tags or [])
        if "customer_whatsapp_consent" in needed:
            facts["customer_whatsapp_consent"] = consent.consent_state(db, customer.id, "whatsapp") == "opted_in"
        if "customer_email_consent" in needed:
            facts["customer_email_consent"] = consent.consent_state(db, customer.id, "email") == "opted_in"
        if "customer_segment" in needed:
            from app.services.messaging import campaigns

            facts["customer_segment"] = campaigns.SEGMENT_LABELS.get(campaigns.segment_by_customer(db).get(customer.id, campaigns.OTHER))
    if payload.get("text") is not None:
        facts["message_text"] = str(payload["text"])[:500]
    if payload.get("item_id"):
        item = db.get(StockItem, payload["item_id"])
        if item is not None:
            facts.update(stock_available=inventory.available(item), stock_item_name=item.name)
    return facts
