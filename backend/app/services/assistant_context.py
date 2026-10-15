"""Build the data summary the AI assistant is allowed to see.

Privacy rule: customer names and email addresses are never included. Individual
customers appear only by their imported customer_id with aggregate figures.
"""

from typing import Any

from app.services import analytics as a

TOP_ROWS = 5
TOP_CUSTOMERS = 10
RECENT_MONTHS = 13

NOT_AVAILABLE = [
    "churn probability (needs a trained model)",
    "predicted CLV (needs a trained model)",
    "revenue forecast (needs a trained model)",
    "growth score (no agreed formula yet)",
    "profit or margins (no cost data is imported)",
]

DEFINITIONS = {
    "asOf": "Latest order date in the data; all windows end on this date.",
    "revenue": "Sum of order values in the last 90 days.",
    "averageClv": "Historical CLV: total revenue to date divided by customers.",
    "retentionRate": "Of customers who bought in the previous 90 days, % who bought again in the last 90 days.",
    "segments": "RFM: 1–5 scores for recency, frequency and spend ranked against all customers.",
    "inactivityLevel": "Rule-based: days since last order divided by the customer's usual gap. Not a prediction.",
    "revenueAtRisk": "Last-12-month spend of customers now At-Risk or Lost. Historical, not a predicted loss.",
    "healthScore": "0–100 from purchase frequency, spending, engagement and activity trend.",
}


def _r(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def build_context(snapshot: a.Snapshot) -> dict[str, Any]:
    values, deltas = a.kpis(snapshot)
    drivers = a.revenue_drivers(snapshot)
    attention = sorted(
        (c for c in snapshot.customers if c.segment == "At-Risk Customers"),
        key=lambda c: c.revenue_12m,
        reverse=True,
    )[:TOP_CUSTOMERS]
    return {
        "dataAsOf": snapshot.as_of.isoformat() if snapshot.as_of else None,
        "customerCount": len(snapshot.customers),
        "kpis": {k: _r(v) for k, v in values.items()},
        "kpiChangesVsPrevious90Days": {
            "totalCustomers_pct": _r(deltas["totalCustomers"], 1),
            "revenue_pct": _r(deltas["revenue"], 1),
            "averageClv_pct": _r(deltas["averageClv"], 1),
            "retentionRate_points": _r(deltas["retentionRate"], 1),
        },
        "segments": [
            {k: _r(v) if isinstance(v, float) else v for k, v in s.items() if k != "avgPredictedClv"}
            for s in a.segment_summaries(snapshot)
        ],
        "monthlyRevenue": a.monthly_revenue(snapshot)[-RECENT_MONTHS:],
        "revenueDriversLast12Months": {
            "byCategory": drivers["byCategory"][:TOP_ROWS],
            "byChannel": drivers["byChannel"][:TOP_ROWS],
            "byCountry": drivers["byCountry"][:TOP_ROWS],
        },
        "newVsReturningLast90Days": drivers["newVsReturning"],
        "revenueAtRiskLast12Months": a.revenue_at_risk(snapshot),
        "healthBands": a.health_distribution(snapshot),
        "inactivityLevels": a.inactivity_distribution(snapshot),
        "recommendations": [
            {k: r[k] for k in ("title", "impact", "targetSegment", "audienceSize", "historicalRevenue", "nextAction")}
            for r in a.recommendations(snapshot)
        ],
        "highestSpendingAtRiskCustomers": [
            {
                "customerId": c.customer_id,
                "daysSinceLastOrder": c.recency_days,
                "usualGapDays": round(c.typical_gap_days),
                "inactivityLevel": c.inactivity_level,
                "spendLast12Months": round(c.revenue_12m, 2),
                "orders": c.orders,
            }
            for c in attention
        ],
        "definitions": DEFINITIONS,
        "notAvailable": NOT_AVAILABLE,
    }
