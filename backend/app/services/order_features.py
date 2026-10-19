"""Order Risk Check: the facts about an order that are known BEFORE it ships.

The one rule of this module is NO DATA LEAKAGE: the features of an order are calculated only
from information that existed at the moment that order was placed. So:
- only orders placed strictly EARLIER count as the customer's history (an order placed at the
  same moment, or later, never does);
- a past order counts as "returned" only if its outcome became known BEFORE the day of the
  current order (a parcel returned next week was not known today);
- the current order's own outcome is never used (it is the label, not a feature).

The functions here are pure (no database, no model), so they are easy to test and to explain.
Missing facts stay missing (None, later NaN), never zero, as in the rest of the app.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time

from app.models.order import OUTCOME_RETURNED

# The order of the numeric columns handed to a model. `country` is text and is encoded by the
# model code, so it is not in this list.
NUMERIC_FEATURES = (
    "past_orders",
    "is_new_customer",
    "past_cancel_rate",
    "days_since_previous_order",
    "value_vs_customer_avg",
    "item_count",
    "distinct_products",
    "hour",
    "weekday",
    "address_length",
    "has_house_number",
    "phone_valid",
)


@dataclass(frozen=True)
class OrderInput:
    """One saved order, as the feature builder needs it."""

    order_id: str
    customer_id: str
    order_date: date
    value: float
    ordered_at: datetime | None = None          # time of day, when the file had it
    item_count: int | None = None
    distinct_products: int | None = None
    country: str | None = None
    address_length: int | None = None
    has_house_number: bool | None = None
    phone_valid: bool | None = None
    outcome: str | None = None                  # "delivered" | "returned" | None (not known)
    outcome_date: date | None = None            # the day the outcome became known
    label_source: str | None = None             # "proxy: cancellations" | "courier data"


@dataclass(frozen=True)
class OrderFeatures:
    order_id: str
    past_orders: int
    is_new_customer: int                        # 1 = no earlier order at all
    past_cancel_rate: float | None              # share of earlier orders KNOWN to be returned
    days_since_previous_order: int | None
    value_vs_customer_avg: float | None         # this order's value / the customer's earlier average
    item_count: int | None
    distinct_products: int | None
    hour: int | None                            # 0-23, only when the order has a time of day
    weekday: int                                # 0 = Monday ... 6 = Sunday
    country: str | None
    address_length: int | None
    has_house_number: int | None                # 1 / 0 / None (no address given)
    phone_valid: int | None

    def numeric_row(self) -> list[float]:
        """The numeric features in `NUMERIC_FEATURES` order; missing values are NaN."""
        return [math.nan if (v := getattr(self, name)) is None else float(v) for name in NUMERIC_FEATURES]


def _placed_at(order: OrderInput) -> datetime:
    """When the order was placed. Without a time of day it counts as the start of its day."""
    return order.ordered_at or datetime.combine(order.order_date, time.min)


def label(order: OrderInput) -> int | None:
    """What the model learns to predict: 1 = returned, 0 = delivered, None = not known."""
    if order.outcome is None:
        return None
    return 1 if order.outcome == OUTCOME_RETURNED else 0


def build_order_features(orders: Iterable[OrderInput]) -> dict[str, OrderFeatures]:
    """Features for every order, keyed by order_id. Each one sees only its customer's EARLIER orders."""
    by_customer: dict[str, list[OrderInput]] = defaultdict(list)
    for order in orders:
        by_customer[order.customer_id].append(order)

    result: dict[str, OrderFeatures] = {}
    for history in by_customer.values():
        history.sort(key=lambda o: (_placed_at(o), o.order_id))
        for index, current in enumerate(history):
            now = _placed_at(current)
            # Strictly earlier only: an order placed at the same moment is NOT history.
            earlier = [p for p in history[:index] if _placed_at(p) < now]
            result[current.order_id] = _features_for(current, earlier)
    return result


def _features_for(current: OrderInput, earlier: list[OrderInput]) -> OrderFeatures:
    count = len(earlier)

    # Count a past return only if it was already known the day before this order's day.
    known_returns = sum(
        1
        for p in earlier
        if p.outcome == OUTCOME_RETURNED and p.outcome_date is not None and p.outcome_date < current.order_date
    )
    average = sum(p.value for p in earlier) / count if count else 0.0

    return OrderFeatures(
        order_id=current.order_id,
        past_orders=count,
        is_new_customer=int(count == 0),
        past_cancel_rate=known_returns / count if count else None,
        days_since_previous_order=(
            (current.order_date - max(p.order_date for p in earlier)).days if count else None
        ),
        value_vs_customer_avg=current.value / average if average > 0 else None,
        item_count=current.item_count,
        distinct_products=current.distinct_products,
        hour=current.ordered_at.hour if current.ordered_at else None,
        weekday=current.order_date.weekday(),
        country=current.country,
        address_length=current.address_length,
        has_house_number=None if current.has_house_number is None else int(current.has_house_number),
        phone_valid=None if current.phone_valid is None else int(current.phone_valid),
    )
