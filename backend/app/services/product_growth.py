"""Which of the seller's own products are selling faster lately? (Trend Finder, part b)

It compares the LAST `days` days with the SAME NUMBER OF DAYS BEFORE THEM (30 vs 30, or 90 vs 90),
counted back from the newest sale in the data (so an old demo file still works).

Where the product numbers come from (the first one that has data):
1. product_sales: units sold per product per week (the table the Season Forecast uses).
2. orders: the product names typed on orders (Add Order, WhatsApp and seller sheets). Each order
   counts once for each product it contains. Orders imported from a store export usually have no
   product names, so they cannot feed this list.
Real data is used when there is any; made-up demo data only when there is nothing else.

Project rule 2: a product is listed only if the two periods TOGETHER have at least MIN_GROUP_COUNT
(20) sales; smaller products are not compared, only counted ("N products have too few sales").
Growth = (last - before) / before. A product that sold nothing before is "new" and has no percentage.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Order
from app.services import data_rules
from app.services.product_sales_import import load_weekly_sales

PERIODS = (30, 90)
MAX_LISTED = 15
MAX_NAME = 120


@dataclass
class GrowthRow:
    product: str
    last: int                          # units (or orders) in the last period
    before: int                        # in the period before it
    growth: float | None               # 0.5 = 50% more; None = new (nothing before)


@dataclass
class GrowthResult:
    days: int
    metric: str                        # "units" (product_sales) or "orders" (product names on orders); "" = no data
    source: str                        # "real", "demo" or ""
    period_end: date | None
    rows: list[GrowthRow] = field(default_factory=list)
    too_small: int = 0                 # products with too few sales to compare
    reason: str | None = None          # "no_data" | "not_enough_history" | None


def split_products(text: str | None) -> list[str]:
    """The product names on an order ("Red shoes, Blue bag" -> two names), tidied and without repeats."""
    names, seen = [], set()
    for part in (text or "").split(","):
        name = re.sub(r"\s+", " ", part).strip()[:MAX_NAME]
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names


def rank(last: dict[str, int], before: dict[str, int]) -> tuple[list[GrowthRow], int]:
    """Pure part: growth rows (fastest first) for products that pass the minimum, and how many did not."""
    rows, small = [], 0
    for product in set(last) | set(before):
        now, then = last.get(product, 0), before.get(product, 0)
        if not data_rules.enough(now + then):
            small += 1
            continue
        if now <= then:
            continue                                   # only products that grew
        rows.append(GrowthRow(product, now, then, (now - then) / then if then else None))
    # "new" products (nothing before) rank by how much they sold, then the rest by growth.
    rows.sort(key=lambda r: (r.growth is None, -(r.growth if r.growth is not None else r.last), -r.last, r.product))
    return rows[:MAX_LISTED], small


def product_growth(db: Session, days: int) -> GrowthResult:
    used, real, demo, sales = load_weekly_sales(db)
    if sales.first is not None and (real + demo) > 0:
        end = sales.data_end
        recent_start = end - timedelta(days=days - 1)
        before_start, before_end = recent_start - timedelta(days=days), recent_start - timedelta(days=1)
        if not sales.covers(before_start, end):
            return GrowthResult(days, "units", used, end, reason="not_enough_history")
        last_units = sales.units_in(recent_start, end)
        before_units = sales.units_in(before_start, before_end)
        rows, small = rank(
            {p: int(u) for p, u in zip(sales.products, last_units) if u > 0},
            {p: int(u) for p, u in zip(sales.products, before_units) if u > 0},
        )
        return GrowthResult(days, "units", used, end, rows, small)

    end = db.scalar(select(func.max(Order.order_date)).where(Order.products.is_not(None)))
    if end is None:
        return GrowthResult(days, "", "", None, reason="no_data")
    recent_start = end - timedelta(days=days - 1)
    before_start = recent_start - timedelta(days=days)
    first = db.scalar(select(func.min(Order.order_date)).where(Order.products.is_not(None)))
    if first is None or first > before_start:
        return GrowthResult(days, "orders", "real", end, reason="not_enough_history")
    last, before, shown = Counter(), Counter(), {}
    for order_date, text in db.execute(select(Order.order_date, Order.products).where(Order.products.is_not(None), Order.order_date >= before_start)):
        bucket = last if order_date >= recent_start else before
        for name in split_products(text):
            shown.setdefault(name.lower(), name)               # "Red shoes" and "red shoes" are one product
            bucket[name.lower()] += 1
    rows, small = rank(dict(last), dict(before))
    for row in rows:
        row.product = shown[row.product]
    return GrowthResult(days, "orders", "real", end, rows, small)
