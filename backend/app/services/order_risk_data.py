"""Load saved orders from PostgreSQL as `OrderInput` rows for the Order Risk feature builder."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Order
from app.services.order_features import OrderInput


def load_order_inputs(db: Session) -> list[OrderInput]:
    rows = db.execute(
        select(
            Order.external_id,
            Customer.external_id,
            Order.order_date,
            Order.order_value,
            Order.ordered_at,
            Order.item_count,
            Order.distinct_products,
            Customer.country,
            Order.address_length,
            Order.has_house_number,
            Order.phone_valid,
            Order.outcome,
            Order.outcome_date,
            Order.label_source,
        ).join(Customer, Customer.id == Order.customer_id)
    )
    return [
        OrderInput(
            order_id=order_id,
            customer_id=customer_id,
            order_date=order_date,
            value=float(value),
            ordered_at=ordered_at,
            item_count=item_count,
            distinct_products=distinct_products,
            country=country,
            address_length=address_length,
            has_house_number=has_house_number,
            phone_valid=phone_valid,
            outcome=outcome,
            outcome_date=outcome_date,
            label_source=label_source,
        )
        for (
            order_id, customer_id, order_date, value, ordered_at, item_count, distinct_products,
            country, address_length, has_house_number, phone_valid, outcome, outcome_date,
            label_source,
        ) in rows
    ]
