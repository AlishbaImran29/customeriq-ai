"""Load imported orders from PostgreSQL into the analytics snapshot."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Order
from app.services.analytics import OrderFact, Snapshot, build_snapshot


def load_snapshot(db: Session) -> Snapshot:
    rows = db.execute(
        select(
            Customer.external_id,
            Customer.first_name,
            Customer.last_name,
            Customer.email,
            Customer.country,
            Order.order_date,
            Order.order_value,
            Order.channel,
            Order.product_category,
            Order.engagement_score,
        ).join(Order, Order.customer_id == Customer.id)
    )
    facts = [
        OrderFact(
            customer_id=external_id,
            name=" ".join(p for p in (first, last) if p) or external_id,
            email=email,
            order_date=order_date,
            value=value,
            channel=channel,
            category=category,
            country=country,
            engagement=engagement,
        )
        for (
            external_id, first, last, email, country,
            order_date, value, channel, category, engagement,
        ) in rows
    ]
    return build_snapshot(facts)
