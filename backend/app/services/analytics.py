"""Descriptive customer analytics computed from imported orders.

Everything here is calculated directly from the data with fixed, documented
formulas (agreed for Phase 3). Nothing in this module is predicted. Churn
probability, predicted CLV and revenue forecasts come from the separate prediction
models in services/predictions.py; the growth score has no agreed formula and is
unavailable.

The reference date ("as of") is the latest order date in the data, so older
imports are analysed relative to their own end date.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

WINDOW_DAYS = 90
YEAR_DAYS = 365
MIN_CUSTOMERS_FOR_SEGMENTS = 20
SINGLE_ORDER_GAP_DAYS = 90
AVG_MONTH_DAYS = 30.44

HEALTH_WEIGHTS = {
    "purchaseFrequency": 0.30,
    "spendingBehavior": 0.30,
    "engagement": 0.20,
    "activityTrend": 0.20,
}
# Used when a customer has no engagement data: engagement is left out (never
# treated as 0) and the other weights are scaled up proportionally.
HEALTH_WEIGHTS_WITHOUT_ENGAGEMENT = {
    "purchaseFrequency": 0.375,
    "spendingBehavior": 0.375,
    "engagement": 0.0,
    "activityTrend": 0.25,
}

HEALTH_BANDS = [  # (min score, label, range text)
    (90, "Excellent", "90–100"),
    (75, "Healthy", "75–89"),
    (55, "Watch", "55–74"),
    (30, "At risk", "30–54"),
    (0, "Critical", "0–29"),
]

SEGMENTS = [
    "Champions",
    "Loyal Customers",
    "Potential Loyalists",
    "At-Risk Customers",
    "Lost Customers",
]

SEGMENT_ACTIONS = {
    "Champions": "Invite to a VIP or referral programme",
    "Loyal Customers": "Offer a loyalty tier upgrade or bundle",
    "Potential Loyalists": "Send a second-purchase incentive",
    "At-Risk Customers": "Send a personalised win-back offer",
    "Lost Customers": "Send a low-cost recovery offer and feedback survey",
}

INACTIVITY_LEVELS = ["Low", "Medium", "High", "Critical"]


# --- input -------------------------------------------------------------------

@dataclass(frozen=True)
class OrderFact:
    customer_id: str
    name: str
    email: str
    order_date: date
    value: Decimal
    channel: str | None
    category: str | None
    country: str | None
    engagement: Decimal | None


# --- per-customer results -----------------------------------------------------

@dataclass
class CustomerMetrics:
    customer_id: str
    name: str
    email: str
    channel: str | None
    country: str | None
    orders: int
    revenue: float
    revenue_12m: float
    first_order: date
    last_order: date
    recency_days: int
    typical_gap_days: float
    activity_ratio: float
    orders_per_month: float
    engagement: float | None
    order_dates: list[date] = field(repr=False, default_factory=list)
    # Filled in by the scoring steps:
    r_score: int = 0
    fm_score: int = 0
    segment: str | None = None
    frequency_factor: float = 0.0
    spending_factor: float = 0.0
    activity_trend: float = 0.0
    health_score: int = 0
    engagement_missing: bool = True
    inactivity_level: str = "Low"
    recommended_action: str = ""


@dataclass
class Snapshot:
    as_of: date | None
    customers: list[CustomerMetrics]
    orders: list[OrderFact]
    segmented: bool

    @property
    def empty(self) -> bool:
        return self.as_of is None


# --- small helpers -------------------------------------------------------------

def round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def midrank_percentiles(values: list[float]) -> list[float]:
    """Percentile 0–100 using mid-ranks, so tied values share one percentile."""
    ordered = sorted(values)
    n = len(ordered)
    result = []
    for v in values:
        less = bisect_left(ordered, v)
        equal = bisect_right(ordered, v) - less
        result.append((less + 0.5 * equal) / n * 100)
    return result


def rank_scale(values: list[float]) -> list[float]:
    """Scale to 0–100 by rank: lowest = 0, highest = 100, ties share the lower rank."""
    n = len(values)
    if n == 1:
        return [50.0]
    ordered = sorted(values)
    return [bisect_left(ordered, v) / (n - 1) * 100 for v in values]


def quintile_score(percentile: float) -> int:
    return min(5, int(percentile // 20) + 1)


def pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current - previous) / previous * 100


# --- building the snapshot -----------------------------------------------------

def build_snapshot(orders: list[OrderFact]) -> Snapshot:
    if not orders:
        return Snapshot(as_of=None, customers=[], orders=[], segmented=False)

    as_of = max(o.order_date for o in orders)
    year_start = as_of - timedelta(days=YEAR_DAYS - 1)

    by_customer: dict[str, list[OrderFact]] = defaultdict(list)
    for order in orders:
        by_customer[order.customer_id].append(order)

    customers: list[CustomerMetrics] = []
    for customer_id, items in by_customer.items():
        items.sort(key=lambda o: o.order_date)
        dates = sorted({o.order_date for o in items})
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        typical_gap = float(median(gaps)) if gaps else float(SINGLE_ORDER_GAP_DAYS)
        typical_gap = max(1.0, typical_gap)
        recency = (as_of - dates[-1]).days
        months_active = max(1.0, (as_of - dates[0]).days / AVG_MONTH_DAYS)
        engagements = [float(o.engagement) for o in items if o.engagement is not None]
        latest = items[-1]
        customers.append(
            CustomerMetrics(
                customer_id=customer_id,
                name=latest.name,
                email=latest.email,
                channel=latest.channel,
                country=latest.country,
                orders=len(items),
                revenue=float(sum(o.value for o in items)),
                revenue_12m=float(sum(o.value for o in items if o.order_date >= year_start)),
                first_order=dates[0],
                last_order=dates[-1],
                recency_days=recency,
                typical_gap_days=typical_gap,
                activity_ratio=recency / typical_gap,
                orders_per_month=len(items) / months_active,
                engagement=sum(engagements) / len(engagements) if engagements else None,
                order_dates=dates,
            )
        )

    segmented = len(customers) >= MIN_CUSTOMERS_FOR_SEGMENTS
    _score_rfm(customers, segmented)
    _score_health(customers)
    for c in customers:
        c.inactivity_level = inactivity_level(c.activity_ratio)
        c.recommended_action = recommended_action(c)
    return Snapshot(as_of=as_of, customers=customers, orders=orders, segmented=segmented)


def _score_rfm(customers: list[CustomerMetrics], segmented: bool) -> None:
    # Fewer days since the last order = more recent = higher score.
    r_pct = midrank_percentiles([-c.recency_days for c in customers])
    f_pct = midrank_percentiles([c.orders for c in customers])
    m_pct = midrank_percentiles([c.revenue for c in customers])
    for c, r, f, m in zip(customers, r_pct, f_pct, m_pct):
        c.r_score = quintile_score(r)
        c.fm_score = round_half_up((quintile_score(f) + quintile_score(m)) / 2)
        c.segment = segment_for(c.r_score, c.fm_score) if segmented else None


def segment_for(r: int, fm: int) -> str:
    """First matching rule wins."""
    if r >= 4 and fm >= 4:
        return "Champions"
    if r >= 3 and fm >= 3:
        return "Loyal Customers"
    if r >= 3:
        return "Potential Loyalists"
    if fm >= 3:
        return "At-Risk Customers"
    return "Lost Customers"


def _score_health(customers: list[CustomerMetrics]) -> None:
    frequency = rank_scale([c.orders_per_month for c in customers])
    spending = rank_scale([c.revenue_12m for c in customers])
    for c, freq, spend in zip(customers, frequency, spending):
        c.frequency_factor = freq
        c.spending_factor = spend
        # Within the usual gap = 100; three times the usual gap or more = 0.
        c.activity_trend = clamp(100 * (3 - c.activity_ratio) / 2)
        c.engagement_missing = c.engagement is None
        weights = HEALTH_WEIGHTS_WITHOUT_ENGAGEMENT if c.engagement_missing else HEALTH_WEIGHTS
        score = (
            weights["purchaseFrequency"] * freq
            + weights["spendingBehavior"] * spend
            + weights["engagement"] * (c.engagement or 0.0)
            + weights["activityTrend"] * c.activity_trend
        )
        c.health_score = round_half_up(clamp(score))


def inactivity_level(ratio: float) -> str:
    """Rule-based (not a prediction): days since last order ÷ usual gap."""
    if ratio <= 1.0:
        return "Low"
    if ratio <= 1.5:
        return "Medium"
    if ratio <= 2.5:
        return "High"
    return "Critical"


def recommended_action(c: CustomerMetrics) -> str:
    if c.segment:
        return SEGMENT_ACTIONS[c.segment]
    if c.inactivity_level == "Low":
        return "Keep in regular campaigns"
    return "Re-engage with a reminder or offer"


def health_band(score: int) -> str:
    for minimum, label, _ in HEALTH_BANDS:
        if score >= minimum:
            return label
    return "Critical"


# --- aggregate views ------------------------------------------------------------

def _window(as_of: date, windows_back: int) -> tuple[date, date]:
    """Inclusive date range of a 90-day window; 0 = the most recent window."""
    end = as_of - timedelta(days=WINDOW_DAYS * windows_back)
    return end - timedelta(days=WINDOW_DAYS - 1), end


def _in(d: date, window: tuple[date, date]) -> bool:
    return window[0] <= d <= window[1]


def kpis(snapshot: Snapshot) -> tuple[dict, dict]:
    """Return (values, deltas). Deltas are None when history is too short."""
    keys = ["totalCustomers", "revenue", "averageClv", "retentionRate", "churnRisk", "growthScore"]
    values: dict[str, float | None] = dict.fromkeys(keys)
    deltas: dict[str, float | None] = dict.fromkeys(keys)
    if snapshot.empty:
        return values, deltas

    as_of = snapshot.as_of
    assert as_of is not None
    first_date = min(o.order_date for o in snapshot.orders)
    current, previous, older = _window(as_of, 0), _window(as_of, 1), _window(as_of, 2)
    covers_previous = first_date <= previous[0]
    covers_older = first_date <= older[0]

    customers = snapshot.customers
    total_revenue = sum(c.revenue for c in customers)
    values["totalCustomers"] = len(customers)
    values["revenue"] = sum(float(o.value) for o in snapshot.orders if _in(o.order_date, current))
    values["averageClv"] = total_revenue / len(customers)

    if covers_previous:
        cutoff = previous[1]
        customers_then = sum(1 for c in customers if c.first_order <= cutoff)
        revenue_then = sum(float(o.value) for o in snapshot.orders if o.order_date <= cutoff)
        previous_revenue = sum(
            float(o.value) for o in snapshot.orders if _in(o.order_date, previous)
        )
        deltas["totalCustomers"] = pct_change(len(customers), customers_then)
        deltas["revenue"] = pct_change(values["revenue"], previous_revenue)
        if customers_then:
            deltas["averageClv"] = pct_change(values["averageClv"], revenue_then / customers_then)
        values["retentionRate"] = retention_rate(customers, previous, current)

    if covers_older and values["retentionRate"] is not None:
        earlier = retention_rate(customers, older, previous)
        if earlier is not None:
            deltas["retentionRate"] = values["retentionRate"] - earlier  # points
    return values, deltas


def retention_rate(
    customers: list[CustomerMetrics], base: tuple[date, date], follow: tuple[date, date]
) -> float | None:
    """% of customers who bought in `base` and bought again in `follow`."""
    cohort = [c for c in customers if any(_in(d, base) for d in c.order_dates)]
    if not cohort:
        return None
    retained = sum(1 for c in cohort if any(_in(d, follow) for d in c.order_dates))
    return retained / len(cohort) * 100


# Growth Score: our own composite of four MEASURED metrics, each turned into a 0-100
# sub-score. It is not an industry standard and is not a prediction. The page shows the
# inputs and weights. Inputs that cannot be measured yet (short history) are left out and
# the remaining weights are scaled up; at least three inputs are needed.
GROWTH_COMPONENTS = [
    ("revenueGrowth", "Revenue growth (last 90 days vs the 90 before)", 0.35),
    ("retention", "Retention rate (90 days)", 0.30),
    ("health", "Average customer health score", 0.20),
    ("customerGrowth", "Customer growth (vs 90 days ago)", 0.15),
]
MIN_GROWTH_INPUTS = 3


def growth_score(snapshot: Snapshot, values: dict, deltas: dict) -> dict | None:
    """0-100 growth score with its breakdown, or None when fewer than three inputs exist.

    Sub-scores: revenue growth -50%..+50% maps to 0..100; customer growth -20%..+20% maps
    to 0..100; retention and health are already 0..100.
    """
    if snapshot.empty or not snapshot.customers:
        return None
    average_health = sum(c.health_score for c in snapshot.customers) / len(snapshot.customers)
    revenue_change, customer_change = deltas.get("revenue"), deltas.get("totalCustomers")
    retention = values.get("retentionRate")
    inputs: dict[str, tuple[float, str] | None] = {
        "revenueGrowth": None if revenue_change is None else (clamp(50 + revenue_change), f"{revenue_change:+.1f}%"),
        "retention": None if retention is None else (clamp(retention), f"{retention:.1f}%"),
        "health": (clamp(average_health), f"{average_health:.0f}/100"),
        "customerGrowth": None if customer_change is None else (clamp(50 + 2.5 * customer_change), f"{customer_change:+.1f}%"),
    }
    used = [(key, label, weight) for key, label, weight in GROWTH_COMPONENTS if inputs[key] is not None]
    if len(used) < MIN_GROWTH_INPUTS:
        return None
    total_weight = sum(weight for _, _, weight in used)
    score = sum(weight * inputs[key][0] for key, _, weight in used) / total_weight  # type: ignore[index]
    return {
        "score": round_half_up(score),
        "components": [
            {
                "key": key,
                "label": label,
                "measure": inputs[key][1],  # type: ignore[index]
                "value": round(inputs[key][0]),  # type: ignore[index]
                "weight": round(weight / total_weight * 100),
            }
            for key, label, weight in used
        ],
        "missing": [label for key, label, _ in GROWTH_COMPONENTS if inputs[key] is None],
    }


def segment_summaries(
    snapshot: Snapshot, predicted_spend: dict[str, float] | None = None
) -> list[dict]:
    """Per-segment totals. With `predicted_spend` (a trained CLV model's next-180-day
    spend per customer), also the average predicted CLV = revenue to date + that spend."""
    if not snapshot.segmented:
        return []
    rows = []
    for name in SEGMENTS:
        members = [c for c in snapshot.customers if c.segment == name]
        revenue = sum(c.revenue for c in members)
        predicted = None
        if predicted_spend is not None and members:
            predicted = (revenue + sum(predicted_spend.get(c.customer_id, 0.0) for c in members)) / len(members)
        rows.append(
            {
                "name": name,
                "customers": len(members),
                "revenue": revenue,
                "avgClv": revenue / len(members) if members else 0.0,
                "avgPredictedClv": predicted,
            }
        )
    return rows


def monthly_revenue(snapshot: Snapshot) -> list[dict]:
    if snapshot.empty:
        return []
    assert snapshot.as_of is not None
    totals: Counter[tuple[int, int]] = Counter()
    for o in snapshot.orders:
        totals[(o.order_date.year, o.order_date.month)] += float(o.value)
    first = min(totals)
    last = (snapshot.as_of.year, snapshot.as_of.month)
    next_day = snapshot.as_of + timedelta(days=1)
    rows = []
    year, month = first
    while (year, month) <= last:
        label = date(year, month, 1).strftime("%b %Y")
        partial = (year, month) == last and next_day.month == snapshot.as_of.month
        rows.append({"month": label, "actual": round(totals[(year, month)], 2), "partial": partial})
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return rows


def _share_rows(totals: dict[str, float], buyers: dict[str, Counter[str]] | None = None) -> list[dict]:
    """Revenue and share per group; with `buyers` (orders per customer in the group) also order counts.

    Repeat rate = share of the group's customers with 2+ orders in the group during the window.
    """
    grand = sum(totals.values())
    rows = []
    for name, value in totals.items():
        row = {"name": name, "revenue": round(value, 2), "share": value / grand * 100 if grand else 0.0}
        counts = buyers.get(name) if buyers else None
        if counts:
            orders = sum(counts.values())
            customers = len(counts)
            row.update(
                orders=orders,
                customers=customers,
                avgOrderValue=round(value / orders, 2),
                repeatRate=sum(1 for n in counts.values() if n >= 2) / customers * 100,
            )
        rows.append(row)
    return sorted(rows, key=lambda r: r["revenue"], reverse=True)


def revenue_drivers(snapshot: Snapshot) -> dict:
    empty = {"byCategory": [], "byChannel": [], "byCountry": [], "newVsReturning": []}
    if snapshot.empty:
        return empty
    assert snapshot.as_of is not None
    year_start = snapshot.as_of - timedelta(days=YEAR_DAYS - 1)
    current = _window(snapshot.as_of, 0)
    first_order = {c.customer_id: c.first_order for c in snapshot.customers}

    by_category: Counter[str] = Counter()
    by_channel: Counter[str] = Counter()
    by_country: Counter[str] = Counter()
    new_vs_returning: Counter[str] = Counter()
    buyers: dict[str, dict[str, Counter[str]]] = {"category": {}, "channel": {}, "country": {}}
    for o in snapshot.orders:
        value = float(o.value)
        if o.order_date >= year_start:
            for dimension, totals, name in (
                ("category", by_category, o.category or "Not specified"),
                ("channel", by_channel, o.channel or "Not specified"),
                ("country", by_country, o.country or "Not specified"),
            ):
                totals[name] += value
                buyers[dimension].setdefault(name, Counter())[o.customer_id] += 1
        if _in(o.order_date, current):
            is_new = _in(first_order[o.customer_id], current)
            new_vs_returning["New customers" if is_new else "Returning customers"] += value
    return {
        "byCategory": _share_rows(by_category, buyers["category"]),
        "byChannel": _share_rows(by_channel, buyers["channel"]),
        "byCountry": _share_rows(by_country, buyers["country"]),
        "newVsReturning": _share_rows(new_vs_returning),
    }


def revenue_at_risk(snapshot: Snapshot) -> list[dict]:
    """Last-12-month revenue of customers now At-Risk or Lost (historical, not a forecast)."""
    if not snapshot.segmented:
        return []
    rows = []
    for name in ("At-Risk Customers", "Lost Customers"):
        members = [c for c in snapshot.customers if c.segment == name]
        rows.append(
            {
                "segment": name,
                "customers": len(members),
                "atRisk": round(sum(c.revenue_12m for c in members), 2),
            }
        )
    return rows


def health_distribution(snapshot: Snapshot) -> list[dict]:
    counts = Counter(health_band(c.health_score) for c in snapshot.customers)
    return [
        {"range": text, "label": label, "customers": counts.get(label, 0)}
        for _, label, text in HEALTH_BANDS
    ]


def inactivity_distribution(snapshot: Snapshot) -> list[dict]:
    counts = Counter(c.inactivity_level for c in snapshot.customers)
    return [{"level": level, "customers": counts.get(level, 0)} for level in INACTIVITY_LEVELS]


_RECOMMENDATION_RULES = [
    # (segment, category, title, detail, next action)
    (
        "At-Risk Customers",
        "Retention Campaign",
        "Win back {n} At-Risk customers",
        "They used to buy often, but their last order was {recency} days ago on average. "
        "They spent {revenue} in the last 12 months.",
        "Send a personalised win-back email or SMS sequence",
    ),
    (
        "Potential Loyalists",
        "Retention Campaign",
        "Turn {n} Potential Loyalists into repeat buyers",
        "Recent customers with few orders so far. They spent {revenue} in the last 12 months.",
        "Trigger a timed second-purchase incentive",
    ),
    (
        "Champions",
        "Upsell",
        "Offer premium or replenishment plans to {n} Champions",
        "Your most recent, frequent, and highest-spending customers. "
        "They spent {revenue} in the last 12 months.",
        "Promote premium products or subscriptions at checkout",
    ),
    (
        "Loyal Customers",
        "Cross-Sell",
        "Recommend complementary products to {n} Loyal Customers",
        "Regular buyers whose favourite category is {category}. "
        "They spent {revenue} in the last 12 months.",
        "Create bundles that pair {category} with other categories",
    ),
    (
        "Lost Customers",
        "Customer Recovery",
        "Recover {n} Lost Customers",
        "No recent orders and low past activity; last order {recency} days ago on average. "
        "They spent {revenue} in the last 12 months.",
        "Send a one-time restart offer with a short feedback survey",
    ),
]


def recommendations(snapshot: Snapshot) -> list[dict]:
    """Fixed rules per segment. No revenue estimates: only historical revenue."""
    if not snapshot.segmented:
        return []
    total_12m = sum(c.revenue_12m for c in snapshot.customers)
    customer_categories: dict[str, Counter[str]] = defaultdict(Counter)
    for o in snapshot.orders:
        if o.category:
            customer_categories[o.customer_id][o.category] += 1

    items = []
    for index, (segment, category, title, detail, action) in enumerate(_RECOMMENDATION_RULES, 1):
        members = [c for c in snapshot.customers if c.segment == segment]
        if not members:
            continue
        revenue_12m = sum(c.revenue_12m for c in members)
        share = revenue_12m / total_12m * 100 if total_12m else 0.0
        categories: Counter[str] = Counter()
        for c in members:
            categories.update(customer_categories[c.customer_id])
        top_category = categories.most_common(1)[0][0] if categories else "their top category"
        fields = {
            "n": f"{len(members):,}",
            "recency": round_half_up(sum(c.recency_days for c in members) / len(members)),
            "revenue": f"${revenue_12m:,.0f}",
            "category": top_category,
        }
        items.append(
            {
                "id": f"REC-{index:02d}",
                "category": category,
                "title": title.format(**fields),
                "detail": detail.format(**fields),
                "impact": "High" if share >= 20 else "Medium" if share >= 8 else "Low",
                "targetSegment": segment,
                "audienceSize": len(members),
                "estimatedRevenue": None,
                "historicalRevenue": round(revenue_12m, 2),
                "nextAction": action.format(**fields),
            }
        )
    order = {"High": 0, "Medium": 1, "Low": 2}
    return sorted(items, key=lambda r: (order[r["impact"]], -r["historicalRevenue"]))


def executive_summary(snapshot: Snapshot, values: dict, deltas: dict) -> dict:
    if snapshot.empty:
        return {"headline": "No data imported yet.", "bullets": [], "method": "rules"}
    assert snapshot.as_of is not None
    bullets = []
    if deltas["revenue"] is not None:
        direction = "up" if deltas["revenue"] >= 0 else "down"
        headline = (
            f"Revenue in the last 90 days is {direction} {abs(deltas['revenue']):.1f}% "
            "on the previous 90 days."
        )
    else:
        headline = f"Customer summary as of {snapshot.as_of:%d %b %Y}."

    if snapshot.segmented:
        champions = [c for c in snapshot.customers if c.segment == "Champions"]
        total_rev = sum(c.revenue for c in snapshot.customers)
        bullets.append(
            f"{len(snapshot.customers):,} customers; Champions are "
            f"{len(champions) / len(snapshot.customers) * 100:.0f}% of customers and "
            f"{sum(c.revenue for c in champions) / total_rev * 100:.0f}% of revenue."
        )
        at_risk = [c for c in snapshot.customers if c.segment == "At-Risk Customers"]
        if at_risk:
            bullets.append(
                f"{len(at_risk):,} At-Risk customers spent "
                f"${sum(c.revenue_12m for c in at_risk):,.0f} in the last 12 months."
            )
    if values["retentionRate"] is not None:
        change = ""
        if deltas["retentionRate"] is not None:
            change = f" ({deltas['retentionRate']:+.1f} pts on the previous window)"
        bullets.append(f"90-day retention is {values['retentionRate']:.1f}%{change}.")
    top = revenue_drivers(snapshot)["byCategory"]
    if top:
        bullets.append(
            f"Top category in the last 12 months: {top[0]['name']} "
            f"({top[0]['share']:.0f}% of revenue)."
        )
    return {"headline": headline, "bullets": bullets, "method": "rules"}
