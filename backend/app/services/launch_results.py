"""Step 6: what really happened after launch, worked out from the seller's own orders.

A launch project is linked to one or more PRODUCT NAMES (table launch_products). An order belongs to the
launch when its product list contains one of those names (case-insensitive) and it was placed on or after
the launch date. Everything below is counted from those orders; nothing is estimated except where it says so.

- orders, revenue (the order value of those orders: an order that also holds other products counts whole),
  customers, and repeat buyers (customers with 2 or more of these orders).
- return rate: returned / (delivered + returned), only when at least MIN_GROUP_COUNT (20) orders have a known
  outcome; otherwise "Not enough data yet" (project rule 2).
- REAL PROFIT VS THE ESTIMATE: the Step 5 costs the seller saved are applied to the real orders. A delivered
  order earns (order value - cost - packing - courier fee); a returned order loses (packing + courier fee +
  return shipping). One unit per order is assumed, which is why it is labelled an estimate. It is compared with
  the Step 5 expectation per order placed. Shown only with enough orders of known outcome.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LaunchProduct, LaunchProject, Order
from app.models.order import LABEL_COURIER
from app.services import data_rules
from app.services.product_growth import split_products
from app.services.profit import ProfitInputs, calculate


def name_key(name: str) -> str:
    return " ".join(name.split()).lower()[:120]


@dataclass
class LaunchResults:
    launched_on: date | None
    linked_products: list[str]
    orders: int = 0
    revenue: float = 0.0
    customers: int = 0
    repeat_buyers: int = 0
    closed_orders: int = 0                       # orders whose outcome (delivered or returned) is known
    return_rate: float | None = None
    return_needed: int = 0                       # more closed orders needed before the rate is shown
    real_profit_per_order: float | None = None   # estimate using the Step 5 costs on real orders
    expected_profit_per_order: float | None = None
    has_profit_inputs: bool = False
    reason: str | None = None                    # not_launched / no_products
    warnings: list[str] = field(default_factory=list)


def orders_for_project(db: Session, project: LaunchProject, keys: set[str], *, courier_only: bool = False) -> list[Order]:
    if not keys or project.launched_on is None:
        return []
    stmt = select(Order).where(Order.products.is_not(None), Order.order_date >= project.launched_on)
    if courier_only:
        stmt = stmt.where(Order.label_source == LABEL_COURIER)
    return [o for o in db.scalars(stmt) if any(name_key(n) in keys for n in split_products(o.products))]


def project_results(db: Session, project: LaunchProject) -> LaunchResults:
    products = list(db.scalars(select(LaunchProduct).where(LaunchProduct.launch_project_id == project.id).order_by(LaunchProduct.name)))
    result = LaunchResults(project.launched_on, [p.name for p in products])
    if project.launched_on is None:
        result.reason = "not_launched"
        return result
    if not products:
        result.reason = "no_products"
        return result
    orders = orders_for_project(db, project, {p.name_key for p in products})
    result.orders = len(orders)
    result.revenue = round(sum(float(o.order_value) for o in orders), 2)
    per_customer: dict[int, int] = {}
    for o in orders:
        per_customer[o.customer_id] = per_customer.get(o.customer_id, 0) + 1
    result.customers = len(per_customer)
    result.repeat_buyers = sum(1 for n in per_customer.values() if n >= 2)

    closed = [o for o in orders if o.outcome in ("delivered", "returned")]
    result.closed_orders = len(closed)
    result.return_needed = data_rules.more_needed(len(closed))
    if not data_rules.enough(len(closed)):
        return result
    result.return_rate = sum(1 for o in closed if o.outcome == "returned") / len(closed)
    if project.profit_inputs:
        result.has_profit_inputs = True
        try:
            inputs = ProfitInputs(**project.profit_inputs)
            result.expected_profit_per_order = calculate(inputs).profit_per_order_placed
            fixed = inputs.cost + inputs.packing + inputs.courier_fee
            lost = inputs.packing + inputs.courier_fee + inputs.return_shipping
            total = sum((float(o.order_value) - fixed) if o.outcome == "delivered" else -lost for o in closed)
            result.real_profit_per_order = round(total / len(closed), 2)
        except (TypeError, ValueError):
            result.has_profit_inputs = False                    # old or broken saved inputs: skip, never guess
    return result
