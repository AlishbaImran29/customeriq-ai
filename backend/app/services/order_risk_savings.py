"""Savings calculator: what could the Order Risk Check have saved on past orders?

It replays the TEST period (orders the model did not learn from) and asks: of the orders the
model flagged as High risk, how many were really returned? Each of those returned parcels cost
the seller the shipping cost both ways, so

    estimated cost avoided = flagged orders that really were returned x shipping cost

This is an ESTIMATE on past data, and the app must say so. It assumes the seller would have
stopped or secured every flagged order that came back (for example by asking for advance
payment). It does not promise future savings, and it also shows the false alarms: flagged
orders that were delivered fine and would have needed extra checking.
"""

import math
from dataclasses import dataclass
from datetime import date

from app.models.order import OUTCOME_RETURNED
from app.services.order_features import OrderInput
from app.services.order_risk_config import FLAGGED_LEVELS, MAX_SHIPPING_COST
from app.services.order_risk_levels import OrderAssessment, assess_orders
from app.services.order_risk_model import OrderRiskResult, orders_tested_on


@dataclass(frozen=True)
class SavingsEstimate:
    shipping_cost: float                  # per parcel, both ways, as typed by the seller
    flagged_levels: tuple[str, ...]
    test_start: date                      # the past period the estimate is based on
    test_end: date
    label_source: str | None              # "proxy: cancellations" or "courier data"
    test_orders: int
    flagged_orders: int                   # test orders the model flagged
    flagged_returned: int                 # ... that really were returned
    false_alarms: int                     # ... that were delivered fine
    total_returned: int                   # all returned orders in the test period
    cost_avoided: float                   # flagged_returned x shipping_cost
    total_return_cost: float              # total_returned x shipping_cost (what returns cost in all)

    @property
    def flagged_precision(self) -> float | None:
        """Share of flagged orders that really came back."""
        return self.flagged_returned / self.flagged_orders if self.flagged_orders else None

    @property
    def returns_caught(self) -> float | None:
        """Share of all returned orders that were flagged."""
        return self.flagged_returned / self.total_returned if self.total_returned else None


def check_shipping_cost(value: float) -> float:
    """The typed shipping cost, or ValueError when it cannot be a real cost."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("The shipping cost must be a number.")
    if not 0 <= value <= MAX_SHIPPING_COST:
        raise ValueError(f"The shipping cost must be between 0 and {MAX_SHIPPING_COST:,.0f}.")
    return float(value)


def count_flagged(
    test_orders: list[OrderInput], assessed: dict[str, OrderAssessment], flagged_levels: tuple[str, ...]
) -> tuple[int, int, int]:
    """(flagged, flagged and really returned, all returned) among the test orders."""
    flagged = flagged_returned = total_returned = 0
    for order in test_orders:
        returned = order.outcome == OUTCOME_RETURNED
        total_returned += returned
        if assessed[order.order_id].level in flagged_levels:
            flagged += 1
            flagged_returned += returned
    return flagged, flagged_returned, total_returned


def savings_estimate(
    result: OrderRiskResult,
    orders: list[OrderInput],
    shipping_cost: float,
    flagged_levels: tuple[str, ...] = FLAGGED_LEVELS,
) -> SavingsEstimate | None:
    """The estimate, or None when the model is not available (no prediction, so no savings)."""
    cost = check_shipping_cost(shipping_cost)
    if not result.available:
        return None
    test_orders = orders_tested_on(result, orders)
    assessed = assess_orders(result, orders)
    flagged, flagged_returned, total_returned = count_flagged(test_orders, assessed, flagged_levels)
    return SavingsEstimate(
        shipping_cost=cost,
        flagged_levels=flagged_levels,
        test_start=min(o.order_date for o in test_orders),
        test_end=max(o.order_date for o in test_orders),
        label_source=result.label_source,
        test_orders=len(test_orders),
        flagged_orders=flagged,
        flagged_returned=flagged_returned,
        false_alarms=flagged - flagged_returned,
        total_returned=total_returned,
        cost_avoided=flagged_returned * cost,
        total_return_cost=total_returned * cost,
    )
