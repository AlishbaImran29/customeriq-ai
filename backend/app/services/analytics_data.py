"""Load imported orders from PostgreSQL into the analytics snapshot."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Customer, Order
from app.services.analytics import OrderFact, Snapshot, build_snapshot
from app.services.channels import CHANNELS


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


def latest_order_date(db: Session) -> date | None:
    return db.scalar(select(func.max(Order.order_date)))


def channel_revenue(db: Session, start: date, end: date) -> list[dict]:
    """Revenue, orders and customers of EVERY channel between two dates (both included), biggest
    first. Channels with no orders are listed with zeros, so the chart always shows all five."""
    rows = db.execute(
        select(
            Order.sales_channel,
            func.coalesce(func.sum(Order.order_value), 0),
            func.count(Order.id),
            func.count(func.distinct(Order.customer_id)),
        )
        .where(Order.order_date >= start, Order.order_date <= end)
        .group_by(Order.sales_channel)
    ).all()
    found = {channel: (float(revenue), int(orders), int(customers)) for channel, revenue, orders, customers in rows}
    result = [
        {"channel": c, "revenue": found.get(c, (0.0, 0, 0))[0], "orders": found.get(c, (0.0, 0, 0))[1],
         "customers": found.get(c, (0.0, 0, 0))[2]}
        for c in CHANNELS
    ]
    return sorted(result, key=lambda r: (-r["revenue"], CHANNELS.index(r["channel"])))
