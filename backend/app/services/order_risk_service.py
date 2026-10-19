"""Everything the Order Risk page needs, worked out once and remembered.

Training and scoring take a few seconds, so the finished report is cached and rebuilt only when
the imported orders change (the same idea as `get_predictions`). Each time the model is retrained
its scores and the trust-rule decision are saved in the database (`order_risk_runs`).
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer
from app.services import order_risk_config as config
from app.services.order_features import OrderInput
from app.services.order_risk_data import load_order_inputs
from app.services.order_risk_levels import LEVELS, OrderAssessment, assess_orders
from app.services.order_risk_model import OrderRiskResult, train_order_risk
from app.services.order_risk_reasons import Reason, explain_orders
from app.services.order_risk_runs import save_run
from app.services.order_risk_savings import SavingsEstimate, savings_estimate
from app.services.whatsapp import whatsapp_number

logger = logging.getLogger(__name__)

_RANK = {"Low": 0, "Medium": 1, "High": 2}


@dataclass(frozen=True)
class OrderRiskRow:
    order_id: str
    order_date: date
    customer_id: str
    customer_name: str
    amount: float
    probability: float
    level: str
    action: str
    reasons: list[Reason]
    whatsapp_phone: str | None      # international digits, None when there is no usable number


@dataclass
class OrderRiskReport:
    result: OrderRiskResult
    as_of: date | None = None
    order_count: int = 0
    customer_count: int = 0
    window_start: date | None = None
    level_counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(LEVELS, 0))
    rows: list[OrderRiskRow] = field(default_factory=list)   # the risky ones first
    window_orders: int = 0
    # Past-data savings counts for the two ways of flagging (None when the model is unavailable).
    savings_high: SavingsEstimate | None = None
    savings_medium_high: SavingsEstimate | None = None


def _fingerprint(orders: list[OrderInput]) -> tuple:
    """Changes whenever an import changes the orders or their outcomes."""
    return (
        len(orders),
        max((o.order_date for o in orders), default=None),
        round(sum(o.value for o in orders), 2),
        sum(o.order_date.toordinal() for o in orders),
        sum(1 for o in orders if o.outcome == "returned"),
        sum(1 for o in orders if o.outcome == "delivered"),
        sum(o.outcome_date.toordinal() for o in orders if o.outcome_date),
    )


_cache: tuple[tuple, OrderRiskReport] | None = None
_lock = threading.Lock()


def clear_cache() -> None:
    global _cache
    with _lock:
        _cache = None


def get_order_risk(db: Session) -> OrderRiskReport:
    """The report for the current orders; retrained (and the run saved) when the data changed."""
    global _cache
    orders = load_order_inputs(db)
    key = _fingerprint(orders)
    with _lock:
        if _cache is not None and _cache[0] == key:
            return _cache[1]
        report = _build(db, orders)
        _cache = (key, report)
        return report


def _build(db: Session, orders: list[OrderInput]) -> OrderRiskReport:
    result = train_order_risk(orders)
    try:
        save_run(db, result)
    except Exception:  # the page must still work if the history cannot be written
        db.rollback()
        logger.exception("Could not save the Order Risk run")
    report = OrderRiskReport(
        result=result,
        as_of=result.as_of,
        order_count=len(orders),
        customer_count=len({o.customer_id for o in orders}),
    )
    if not result.available:
        return report

    assessed = assess_orders(result, orders)
    report.savings_high = savings_estimate(result, orders, 1.0, ("High",), assessed)
    report.savings_medium_high = savings_estimate(result, orders, 1.0, ("High", "Medium"), assessed)

    report.window_start = result.as_of - timedelta(days=config.RECENT_DAYS)
    window = [o for o in orders if o.order_date > report.window_start]
    report.window_orders = len(window)
    for o in window:
        report.level_counts[assessed[o.order_id].level] += 1

    reasons = explain_orders(result, orders, {o.order_id for o in window})
    people = _customer_details(db, {o.customer_id for o in window})
    rows = []
    for o in window:
        a: OrderAssessment = assessed[o.order_id]
        name, phone = people.get(o.customer_id, (o.customer_id, None))
        rows.append(OrderRiskRow(
            o.order_id, o.order_date, o.customer_id, name, o.value, a.probability, a.level, a.action,
            reasons.get(o.order_id, []), whatsapp_number(phone),
        ))
    # The orders that need action come first: High, then Medium, then Low; newest first within a level.
    rows.sort(key=lambda r: (-_RANK[r.level], -r.order_date.toordinal(), -r.probability))
    report.rows = rows
    return report


def _customer_details(db: Session, customer_ids: set[str]) -> dict[str, tuple[str, str | None]]:
    """customer_id -> (name, phone) for the customers in the window."""
    details = {}
    ids = list(customer_ids)
    for start in range(0, len(ids), 1000):
        batch = ids[start : start + 1000]
        for external_id, first, last, phone in db.execute(
            select(Customer.external_id, Customer.first_name, Customer.last_name, Customer.phone)
            .where(Customer.external_id.in_(batch))
        ):
            details[external_id] = (" ".join(p for p in (first, last) if p) or external_id, phone)
    return details
