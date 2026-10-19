"""Request and response shapes for Quick Order Entry (camelCase, matching frontend/lib/api/orders.ts).

The request is deliberately loose: the values are checked by `services/quick_order.py`, which
reports every problem at once, field by field, with a plain message.
"""

from datetime import date
from typing import Any

from app.schemas.imports import CamelModel


class QuickOrderIn(CamelModel):
    customer_name: Any = None
    phone: Any = None
    city: Any = None
    products: Any = None            # a list of product names
    amount: Any = None
    payment_type: Any = None        # "cod" | "prepaid"
    channel: Any = None             # instagram | whatsapp | facebook | website | other
    order_date: Any = None          # YYYY-MM-DD; today when left out
    note: Any = None


class QuickOrderOut(CamelModel):
    order_id: str
    customer_id: str
    customer_name: str
    phone: str                      # +923XXXXXXXXX
    returning: bool                 # the number already belonged to a customer
    customer_orders: int            # that customer's orders, including this one


class CustomerLookupOut(CamelModel):
    """What the phone box shows while the seller types: is this a returning customer?"""

    valid: bool                     # the text is a Pakistani mobile number
    phone: str | None               # +923XXXXXXXXX when valid
    found: bool
    name: str | None
    orders: int
    last_order_date: date | None
    last_city: str | None
