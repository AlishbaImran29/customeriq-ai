"""Load imported orders from PostgreSQL into the analytics snapshot."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Order
from app.services.analytics import OrderFact, Snapshot, build_snapshot


def load_snapshot(db: Session, channel: str | None = None) -> Snapshot:
    """The orders as the analytics need them. With `channel`, only that channel's orders: every
    figure (segments, churn, cohorts, health, models) is then calculated for that channel alone."""
    query = select(
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
        Order.sales_channel,
    ).join(Order, Order.customer_id == Customer.id)
    if channel:
        query = query.where(Order.sales_channel == channel)
    facts = [
        OrderFact(
            customer_id=external_id,
            name=" ".join(p for p in (first, last) if p) or external_id,
            email=email,
            order_date=order_date,
            value=value,
            channel=order_channel,
            category=category,
            country=country,
            engagement=engagement,
            sales_channel=sales_channel,
        )
        for (
            external_id, first, last, email, country,
            order_date, value, order_channel, category, engagement, sales_channel,
        ) in db.execute(query)
    ]
    return build_snapshot(facts)
