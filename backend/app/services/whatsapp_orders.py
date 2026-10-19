"""Save the orders a seller ACCEPTED from a WhatsApp chat, and delete them again.

Privacy rules, the same ones the page promises:
- Only the order's own fields are saved: name, phone, city, products, amount, payment type, the
  date, and the channel (always WhatsApp). The chat text is never stored, and not even sent here.
- Every order gets a marker (`orders.source = "whatsapp_chat"`) so all of them can be deleted.

Importing the same chat twice adds nothing: an order's id is a fingerprint of its phone, date,
amount and the time of its first message (a hash, so it holds no text), and an id that already
exists is skipped.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import Customer, Order
from app.services.quick_order import CleanOrder, check_quick_order, create_quick_order

SOURCE = "whatsapp_chat"
MAX_ORDERS_PER_SAVE = 500


@dataclass(frozen=True)
class SaveResult:
    saved: int
    already_imported: int
    new_customers: int


def order_fingerprint(phone: str, order_date: str, amount: str, message_time: datetime) -> str:
    """The id of an imported order: the same chat order always gives the same id."""
    raw = f"{phone}|{order_date}|{amount}|{message_time.isoformat()}"
    return "WA-" + hashlib.sha256(raw.encode()).hexdigest()[:14].upper()


def _check_rows(rows: list[dict[str, Any]]) -> tuple[list[tuple[CleanOrder, datetime]], dict[str, dict[str, str]]]:
    """Check every row. Returns the clean orders, or the problems keyed by row number."""
    clean_rows: list[tuple[CleanOrder, datetime]] = []
    problems: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows):
        # The channel is always WhatsApp here; whatever the page sent is ignored.
        clean, errors = check_quick_order({**row, "channel": "whatsapp", "note": None})
        moment = None
        try:
            moment = datetime.fromisoformat(str(row.get("messageTime")))
        except ValueError:
            errors = {**errors, "messageTime": "Enter the time of the message."}
        if clean is None or moment is None:
            problems[str(index)] = errors
        else:
            clean_rows.append((clean, moment))
    return clean_rows, problems


def save_accepted_orders(db: Session, rows: list[dict[str, Any]]) -> SaveResult:
    """Save the accepted orders, all or none. Problems come back by row, and nothing is saved."""
    if not rows:
        raise ApiError(422, "no_orders", "There are no accepted orders to save.")
    if len(rows) > MAX_ORDERS_PER_SAVE:
        raise ApiError(422, "too_many_orders", f"Save at most {MAX_ORDERS_PER_SAVE} orders at a time.")
    clean_rows, problems = _check_rows(rows)
    if problems:
        raise ApiError(422, "invalid_orders", "Some orders need attention.", {"rows": problems})

    saved = skipped = new_customers = 0
    try:
        for clean, moment in clean_rows:
            order_id = order_fingerprint(clean.phone, clean.order_date.isoformat(), str(clean.amount), moment)
            result = create_quick_order(db, clean, order_id=order_id, source=SOURCE, commit=False)
            if result is None:
                skipped += 1
                continue
            saved += 1
            new_customers += 0 if result.returning else 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return SaveResult(saved, skipped, new_customers)


def summary(db: Session) -> tuple[int, int]:
    """(orders, customers) that came from WhatsApp chats."""
    orders = db.scalar(select(func.count()).select_from(Order).where(Order.source == SOURCE)) or 0
    customers = db.scalar(select(func.count(func.distinct(Order.customer_id))).where(Order.source == SOURCE)) or 0
    return int(orders), int(customers)


def delete_all(db: Session) -> tuple[int, int]:
    """Delete every order imported from a WhatsApp chat, and the customers who then have no orders.
    Orders from files or the form are never touched. Returns (orders deleted, customers deleted)."""
    orders = db.execute(delete(Order).where(Order.source == SOURCE)).rowcount or 0
    customers = db.execute(
        delete(Customer).where(~exists().where(Order.customer_id == Customer.id))
    ).rowcount or 0
    db.commit()
    return int(orders), int(customers)
