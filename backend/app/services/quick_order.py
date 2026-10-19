"""Quick Order Entry: one order typed in by hand (about 10 seconds on a phone).

A seller on Instagram or WhatsApp has no export file; the order is in a chat. This module checks
what was typed and saves it as an ordinary order, so it flows into the same analytics as every
imported order. The customer is found by PHONE NUMBER (see `customer_identity.py`): the same
person typed as 0300-1234567 and +92 300 1234567 is one customer.

Checking is done by hand (not by the framework) so that EVERY problem is reported at once, field
by field, in plain words; the page shows each message next to its field.
"""

import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import Customer, Order
from app.services.channels import CHANNELS
from app.services.phone import NOT_A_PK_MOBILE, normalise_pk_phone

PAYMENT_TYPES = ("cod", "prepaid")
MAX_AMOUNT = Decimal("9999999.99")
MAX_PRODUCTS = 20
EARLIEST_DATE = date(2000, 1, 1)
DUPLICATE_WINDOW_SECONDS = 60
_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O or 1/I: easy to read out loud


@dataclass(frozen=True)
class CleanOrder:
    """A quick order after checking: every value is valid and in its final form."""

    customer_name: str
    phone: str                  # +923XXXXXXXXX
    city: str
    products: list[str]
    amount: Decimal
    payment_type: str           # "cod" | "prepaid"
    channel: str                # one of CHANNELS
    order_date: date
    note: str | None


@dataclass(frozen=True)
class QuickOrderResult:
    order_id: str
    customer_id: str
    customer_name: str
    phone: str
    returning: bool             # the number already belonged to a customer
    customer_orders: int        # that customer's orders, including this one


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def check_quick_order(data: dict[str, Any]) -> tuple[CleanOrder | None, dict[str, str]]:
    """Check what the seller typed. Returns the clean order, or the problems keyed by field."""
    errors: dict[str, str] = {}

    name = _text(data.get("customerName"))
    if not name:
        errors["customerName"] = "Enter the customer's name."
    elif len(name) > 100:
        errors["customerName"] = "The name is too long (100 characters at most)."

    phone = normalise_pk_phone(_text(data.get("phone")))
    if not _text(data.get("phone")):
        errors["phone"] = "Enter the customer's phone number."
    elif phone is None:
        errors["phone"] = NOT_A_PK_MOBILE

    city = _text(data.get("city"))
    if not city:
        errors["city"] = "Enter the city."
    elif len(city) > 100:
        errors["city"] = "The city name is too long."

    products, problem = _check_products(data.get("products"))
    if problem:
        errors["products"] = problem

    amount, problem = _check_amount(data.get("amount"))
    if problem:
        errors["amount"] = problem

    payment = _text(data.get("paymentType")).lower()
    if payment not in PAYMENT_TYPES:
        errors["paymentType"] = "Choose COD or prepaid."

    channel = _text(data.get("channel")).lower()
    if channel not in CHANNELS:
        errors["channel"] = "Choose where the order came from."

    order_date, problem = _check_date(data.get("orderDate"))
    if problem:
        errors["orderDate"] = problem

    note = _text(data.get("note")) or None
    if note and len(note) > 500:
        errors["note"] = "The note is too long (500 characters at most)."

    if errors:
        return None, errors
    return CleanOrder(name, phone, city, products, amount, payment, channel, order_date, note), {}


def _check_products(raw: Any) -> tuple[list[str], str | None]:
    if not isinstance(raw, list):
        return [], "Add at least one product."
    seen: set[str] = set()
    products: list[str] = []
    for item in raw:
        name = _text(item)
        if not name or name.lower() in seen:
            continue                                   # blanks and repeats are dropped, not errors
        if len(name) > 100:
            return [], "A product name is too long (100 characters at most)."
        seen.add(name.lower())
        products.append(name)
    if not products:
        return [], "Add at least one product."
    if len(products) > MAX_PRODUCTS:
        return [], f"Add at most {MAX_PRODUCTS} products."
    return products, None


def _check_amount(raw: Any) -> tuple[Decimal, str | None]:
    zero = Decimal(0)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return zero, "Enter the amount."
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return zero, "Enter the amount as a number, like 2500."
    try:
        value = Decimal(raw.replace(",", "").strip()) if isinstance(raw, str) else Decimal(str(raw))
    except InvalidOperation:
        return zero, "Enter the amount as a number, like 2500."
    if not value.is_finite():
        return zero, "Enter the amount as a number, like 2500."
    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if value <= 0:
        return zero, "The amount must be more than 0."
    if value > MAX_AMOUNT:
        return zero, "The amount is too large."
    return value, None


def _check_date(raw: Any) -> tuple[date, str | None]:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return _today(), None                          # the default is today
    try:
        day = date.fromisoformat(_text(raw))
    except ValueError:
        return _today(), "Enter the date as YYYY-MM-DD."
    # One day of slack: a phone in Pakistan can already be on tomorrow's date while it is still
    # today in UTC.
    if day > _today() + timedelta(days=1):
        return _today(), "The date is in the future."
    if day < EARLIEST_DATE:
        return _today(), "The date is too far in the past."
    return day, None


def find_customer(db: Session, phone: str) -> Customer | None:
    """The customer who owns this number: saved with it, or whose id IS the number."""
    return db.scalar(
        select(Customer)
        .where((Customer.phone_normalised == phone) | (Customer.external_id == phone))
        .order_by(Customer.phone_normalised.is_(None))   # a customer with the number saved wins
        .limit(1)
    )


def _new_order_id(day: date) -> str:
    return f"QO-{day:%Y%m%d}-" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(5))


def create_quick_order(
    db: Session, order: CleanOrder, *, order_id: str | None = None, source: str | None = None, commit: bool = True
) -> QuickOrderResult | None:
    """Save the order, creating the customer when this phone number is new.

    With an explicit `order_id` (the WhatsApp import makes one from the order itself) an order that
    already exists is skipped and None is returned, so importing the same chat twice adds nothing.
    `commit=False` leaves the transaction open so a whole batch is saved, or none of it.
    """
    if order_id is not None and db.scalar(select(Order.id).where(Order.external_id == order_id)) is not None:
        return None
    customer = find_customer(db, order.phone)
    returning = customer is not None
    if customer is None:
        customer = Customer(
            external_id=order.phone, first_name=order.customer_name, phone=order.phone,
            phone_normalised=order.phone, country="Pakistan",
        )
        db.add(customer)
        db.flush()
    else:
        if customer.phone_normalised is None:
            customer.phone_normalised = order.phone     # an older customer whose id was the number
        if not customer.first_name:
            customer.first_name = order.customer_name   # never overwrite a name that is already there

    products = ", ".join(order.products)
    since = func.now() - timedelta(seconds=DUPLICATE_WINDOW_SECONDS)
    twin = None if order_id is not None else db.scalar(
        select(Order.id).where(
            Order.customer_id == customer.id, Order.order_date == order.order_date,
            Order.order_value == order.amount, Order.products == products, Order.created_at > since,
        ).limit(1)
    )
    if twin is not None:
        db.rollback()
        raise ApiError(
            409, "duplicate_order",
            "This looks like the order you just added (same customer, amount and products). "
            "If it is a different order, change something and save again.",
        )

    # A given id is used as it is; otherwise a random one, retried on the rare clash.
    for _ in range(1 if order_id is not None else 5):
        new_id = order_id or _new_order_id(order.order_date)
        try:
            with db.begin_nested():
                db.add(Order(
                    external_id=new_id, customer_id=customer.id, order_date=order.order_date,
                    order_value=order.amount, channel=order.channel.capitalize(), sales_channel=order.channel,
                    payment_type=order.payment_type, city=order.city, products=products, note=order.note,
                    source=source,
                ))
            order_id = new_id
            break
        except IntegrityError:
            continue
    else:
        raise ApiError(503, "service_unavailable", "Could not save the order. Please try again.")

    db.flush()
    count = db.scalar(select(func.count()).select_from(Order).where(Order.customer_id == customer.id))
    if commit:
        db.commit()
    name = customer.first_name or customer.external_id
    return QuickOrderResult(order_id, customer.external_id, name, order.phone, returning, int(count or 0))
