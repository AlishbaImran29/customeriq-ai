"""Profit and the shop's other money numbers. EVERY definition lives in this one file (see DEFINITIONS).

REAL PROFIT PER ORDER  =  revenue  -  product cost  -  packing  -  courier fee  -  return shipping  -  ad cost (estimate)

by what happened to the parcel (the same cash-on-delivery model as the Launch Studio Profit Check):
- DELIVERED  revenue = the order value;      product cost counts (it was sold).
- RETURNED   revenue = 0;                    product cost does NOT count (the goods come back to the shelf);
             the courier fee out, the packing and the RETURN SHIPPING are lost.
- LOST       revenue = 0;                    the product cost IS lost with the parcel; fee and packing too.
- PENDING    not counted yet: nothing has happened to the parcel, so there is no profit to report.

HONESTY RULES
- A cost the shop has not entered is "unknown", never a silent zero. An order whose PRODUCT COST is unknown (the item is not in
  Inventory, or has no cost price) is left out of the profit totals and counted as "cost unknown". Packing and return shipping
  that were never entered are reported as missing.
- Ad cost is an ESTIMATE: each sales channel's ad spend in the period is shared equally over that channel's orders.
- A rate or an average (margin, return rate, profit per order) of a group is shown only when the group has at least
  MIN_GROUP_COUNT orders; sums are always shown. Dates are Asia/Karachi days.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Customer, Order, OrderStatusHistory, Shipment
from app.models.inventory import StockItem
from app.models.profit import AdSpend, BusinessSettings
from app.services import data_rules, inventory

KARACHI = ZoneInfo("Asia/Karachi")
MAX_ORDERS = 20_000
ZERO = Decimal("0")

DEFINITIONS = [
    {"name": "Gross order revenue", "formula": "The total value of every order placed in the period, whatever happened to the parcel."},
    {"name": "Delivered revenue", "formula": "The value of orders that were delivered and not returned."},
    {"name": "Collected cash (prepaid)", "formula": "The value of delivered prepaid orders. COD cash is on the Cash Tracker: it is only collected when the courier pays you."},
    {"name": "Real profit per order", "formula": "Revenue - product cost - packing - courier fee - return shipping - ad cost. Returned orders earn nothing and lose the fees; lost parcels also lose the product."},
    {"name": "Return rate", "formula": "Returned orders / (delivered + returned + lost orders). Orders still on the way are not counted."},
    {"name": "Failed delivery rate", "formula": "Lost parcels / shipments that ended (delivered, returned or lost)."},
    {"name": "Repeat purchase rate", "formula": "Customers who ordered in the period AND had ordered before / customers who ordered in the period."},
    {"name": "Ad cost per order", "formula": "ESTIMATE: a channel's ad spend in the period / that channel's orders in the period."},
]


@dataclass
class OrderFacts:
    id: int
    number: str
    day: date
    channel: str
    city: str | None
    courier: str | None
    customer_id: int
    customer_name: str
    value: Decimal
    payment_type: str | None
    fate: str                              # delivered | returned | lost | pending
    items: list[tuple[str, int]] = field(default_factory=list)
    product_cost: Decimal | None = None    # None = unknown
    courier_fee: Decimal | None = None     # None = no fee on record


@dataclass
class OrderPnL:
    facts: OrderFacts
    revenue: Decimal = ZERO
    product_cost: Decimal = ZERO
    packing: Decimal = ZERO
    courier_fee: Decimal = ZERO
    return_shipping: Decimal = ZERO
    ad_cost: Decimal = ZERO
    profit: Decimal = ZERO
    counted: bool = False
    missing: list[str] = field(default_factory=list)


def order_pnl(f: OrderFacts, packing: Decimal | None, return_shipping: Decimal | None, ad_cost: Decimal) -> OrderPnL:
    """The profit of ONE order. Pure arithmetic, no database."""
    p = OrderPnL(facts=f)
    if f.fate == "pending":
        return p
    if packing is None:
        p.missing.append("packing")
    if f.courier_fee is None:
        p.missing.append("courier_fee")
    p.packing, p.courier_fee, p.ad_cost = packing or ZERO, f.courier_fee or ZERO, ad_cost
    if f.fate == "delivered":
        p.revenue = f.value
    if f.fate == "returned":
        if return_shipping is None:
            p.missing.append("return_shipping")
        p.return_shipping = return_shipping or ZERO
    if f.fate in ("delivered", "lost"):                       # the product was sold, or lost with the parcel
        if f.product_cost is None:
            p.missing.append("product_cost")
        p.product_cost = f.product_cost or ZERO
    p.counted = "product_cost" not in p.missing
    p.profit = p.revenue - p.product_cost - p.packing - p.courier_fee - p.return_shipping - p.ad_cost
    return p


@dataclass
class Group:
    key: str
    orders: int = 0                  # orders that ended (counted in profit)
    revenue: Decimal = ZERO
    profit: Decimal = ZERO
    returned: int = 0
    ended: int = 0
    enough: bool = False
    margin: float | None = None
    profit_per_order: float | None = None
    return_rate: float | None = None


def _group(rows: list[tuple[str, OrderPnL, Decimal]]) -> list[Group]:
    """rows are (key, order profit, share of that order in 0..1). Sums always; rates only for big enough groups."""
    groups: dict[str, Group] = {}
    for key, p, share in rows:
        g = groups.setdefault(key, Group(key))
        g.ended += 1 if share > 0 else 0
        g.returned += 1 if p.facts.fate == "returned" and share > 0 else 0
        if p.counted:
            g.orders += 1
            g.revenue += p.revenue * share
            g.profit += p.profit * share
    for g in groups.values():
        g.enough = data_rules.enough(g.orders)
        if g.enough:
            g.profit_per_order = float(g.profit / g.orders)
            g.margin = float(g.profit / g.revenue) if g.revenue > 0 else None
        if data_rules.enough(g.ended):
            g.return_rate = g.returned / g.ended
    return sorted(groups.values(), key=lambda g: g.profit, reverse=True)


@dataclass
class Analysis:
    start: date
    end: date
    placed: int = 0
    gross_revenue: Decimal = ZERO
    delivered_revenue: Decimal = ZERO
    prepaid_collected: Decimal = ZERO
    counted: int = 0
    profit: Decimal = ZERO
    ad_spend: Decimal = ZERO
    cost_unknown: int = 0
    pending: int = 0
    missing: dict[str, int] = field(default_factory=dict)
    return_rate: float | None = None
    failed_delivery_rate: float | None = None
    repeat_purchase_rate: float | None = None
    low_stock: int = 0
    ended: int = 0
    by_channel: list[Group] = field(default_factory=list)
    by_city: list[Group] = field(default_factory=list)
    by_courier: list[Group] = field(default_factory=list)
    by_product: list[Group] = field(default_factory=list)
    by_customer: list[Group] = field(default_factory=list)
    revenue_by_channel: dict[str, Decimal] = field(default_factory=dict)
    packing_set: bool = False
    return_shipping_set: bool = False


def today_karachi(now: datetime | None = None) -> date:
    return (now or datetime.now(KARACHI)).astimezone(KARACHI).date()


def get_settings(db: Session) -> BusinessSettings:
    row = db.scalar(select(BusinessSettings).limit(1))
    if row is None:
        row = BusinessSettings()
        db.add(row)
        db.flush()
    return row


def _fate(order: Order, shipment: Shipment | None, status: str | None) -> str:
    if shipment is not None:
        mapped = {"delivered": "delivered", "returned": "returned", "lost": "lost"}.get(shipment.status)
        if mapped:
            return mapped
    if order.outcome in ("delivered", "returned"):
        return order.outcome
    return {"delivered": "delivered", "returned": "returned"}.get(status or "", "pending")


def load_facts(db: Session, start: date, end: date) -> list[OrderFacts]:
    orders = list(db.execute(
        select(Order, Customer).join(Customer, Customer.id == Order.customer_id)
        .where(Order.order_date >= start, Order.order_date <= end).order_by(Order.order_date, Order.id).limit(MAX_ORDERS)
    ))
    ids = [o.id for o, _ in orders]
    shipments: dict[int, Shipment] = {}
    statuses: dict[int, str] = {}
    for start_at in range(0, len(ids), 1000):
        batch = ids[start_at:start_at + 1000]
        for s in db.scalars(select(Shipment).where(Shipment.order_id.in_(batch)).order_by(Shipment.id)):
            shipments[s.order_id] = s
        for oid, st in db.execute(select(OrderStatusHistory.order_id, OrderStatusHistory.status).where(OrderStatusHistory.order_id.in_(batch)).order_by(OrderStatusHistory.at, OrderStatusHistory.id)):
            statuses[oid] = st
    stock = list(db.scalars(select(StockItem)))
    by_key: dict[str, StockItem] = {}
    for item in stock:
        by_key[item.sku.lower()] = item
        by_key.setdefault(item.name.lower(), item)
    facts = []
    for order, customer in orders:
        ship = shipments.get(order.id)
        lines = inventory.parse_lines(order.products)
        cost: Decimal | None = ZERO
        for name, qty in lines:
            item = by_key.get(name.lower())
            if item is None or item.cost_price is None:
                cost = None
                break
            cost += item.cost_price * qty
        if not lines:
            cost = None
        facts.append(OrderFacts(
            id=order.id, number=order.external_id, day=order.order_date, channel=order.sales_channel or "other", city=order.city or (ship.city if ship else None),
            courier=ship.courier if ship else None, customer_id=customer.id, customer_name=" ".join(p for p in (customer.first_name, customer.last_name) if p) or customer.external_id,
            value=order.order_value, payment_type=order.payment_type, fate=_fate(order, ship, statuses.get(order.id)), items=lines, product_cost=cost, courier_fee=ship.courier_fee if ship else None,
        ))
    return facts


def analyze(db: Session, start: date, end: date) -> Analysis:
    settings = get_settings(db)
    facts = load_facts(db, start, end)
    spend: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for channel, amount in db.execute(select(AdSpend.channel, func.sum(AdSpend.amount)).where(AdSpend.spend_date >= start, AdSpend.spend_date <= end).group_by(AdSpend.channel)):
        spend[channel] = amount
    per_channel = defaultdict(int)
    for f in facts:
        per_channel[f.channel] += 1
    result = Analysis(start=start, end=end, placed=len(facts), ad_spend=sum(spend.values(), ZERO), packing_set=settings.packing_cost is not None, return_shipping_set=settings.return_shipping_cost is not None)
    pnls = []
    for f in facts:
        ad = spend[f.channel] / per_channel[f.channel] if per_channel[f.channel] and f.fate != "pending" else ZERO
        pnls.append(order_pnl(f, settings.packing_cost, settings.return_shipping_cost, ad))
        result.gross_revenue += f.value
        result.revenue_by_channel[f.channel] = result.revenue_by_channel.get(f.channel, ZERO) + f.value
    returned = delivered = lost = 0
    for p in pnls:
        f = p.facts
        if f.fate == "pending":
            result.pending += 1
            continue
        result.ended += 1
        delivered += f.fate == "delivered"
        returned += f.fate == "returned"
        lost += f.fate == "lost"
        if f.fate == "delivered":
            result.delivered_revenue += f.value
            if f.payment_type == "prepaid":
                result.prepaid_collected += f.value
        for m in p.missing:
            result.missing[m] = result.missing.get(m, 0) + 1
        if p.counted:
            result.counted += 1
            result.profit += p.profit
        else:
            result.cost_unknown += 1
    if data_rules.enough(result.ended):
        result.return_rate = (returned + lost) / result.ended
    shipped = delivered + returned + lost
    result.failed_delivery_rate = lost / shipped if data_rules.enough(shipped) else None
    result.low_stock = sum(1 for i in db.scalars(select(StockItem)) if inventory.is_low(i))
    result.repeat_purchase_rate = _repeat_rate(db, facts)

    def rows(key_of):
        return [(key_of(p.facts), p, Decimal(1)) for p in pnls if p.facts.fate != "pending"]

    result.by_channel = _group(rows(lambda f: f.channel))
    result.by_city = _group(rows(lambda f: f.city or "Unknown"))
    result.by_courier = _group(rows(lambda f: f.courier or "No courier on record"))
    result.by_customer = _group(rows(lambda f: f.customer_name))[:10]
    product_rows = []
    for p in pnls:
        if p.facts.fate == "pending":
            continue
        units = sum(q for _, q in p.facts.items) or 1
        for name, qty in p.facts.items or [("(no product written)", 1)]:
            product_rows.append((name.title(), p, Decimal(qty) / Decimal(units)))
    result.by_product = _group(product_rows)
    return result


def _repeat_rate(db: Session, facts: list[OrderFacts]) -> float | None:
    customers = {f.customer_id for f in facts}
    if not data_rules.enough(len(customers)):
        return None
    earlier = {cid for (cid,) in db.execute(select(Order.customer_id).where(Order.customer_id.in_(customers), Order.order_date < min(f.day for f in facts)).distinct())}
    inside: dict[int, int] = defaultdict(int)
    for f in facts:
        inside[f.customer_id] += 1
    repeaters = {cid for cid in customers if cid in earlier or inside[cid] > 1}
    return len(repeaters) / len(customers)


def default_range(now: datetime | None = None, days: int = 30) -> tuple[date, date]:
    end = today_karachi(now)
    return end - timedelta(days=days - 1), end
