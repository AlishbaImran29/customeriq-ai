"""Build the data summary the AI assistant is allowed to see.

Privacy rule: customer names and email addresses are never included. Individual
customers appear only by their imported customer_id with aggregate figures.
"""

from typing import Any

from app.services import analytics as a
from app.services import predictions as pr

TOP_ROWS = 5
TOP_CUSTOMERS = 10
RECENT_MONTHS = 13

ALWAYS_NOT_AVAILABLE = [
    "profit or margins (no cost data is imported)",
    "predicted customer lifetime value and revenue forecast (they did not beat a simple baseline, so they were removed)",
]

DEFINITIONS = {
    "asOf": "Latest order date in the data; all windows end on this date.",
    "revenue": "Sum of order values in the last 90 days.",
    "averageClv": "Historical CLV: total revenue to date divided by customers.",
    "retentionRate": "Of customers who bought in the previous 90 days, % who bought again in the last 90 days.",
    "segments": "RFM: 1–5 scores for recency, frequency and spend ranked against all customers.",
    "inactivityLevel": "Rule-based: days since last order divided by the customer's usual gap. Not a prediction.",
    "revenueAtRisk": "Last-12-month spend of customers now At-Risk or Lost. Historical, not a predicted loss.",
    "growthScore": "Our own 0-100 composite of revenue growth, retention and customer growth (see growthScoreBreakdown). Not an industry standard and not a prediction.",
    "churnProbability": "Model estimate of the chance a customer places no order in the next 90 days. Not a certainty.",
}


def _not_available(preds: pr.Predictions, growth: dict | None) -> list[str]:
    missing = list(ALWAYS_NOT_AVAILABLE)
    if growth is None:
        missing.append("growth score (needs at least two of its three inputs, i.e. 180+ days of history)")
    if not preds.churn.available:
        missing.append(f"churn probability ({preds.churn.reason})")
    return missing


def _model_summary(model: pr.ModelResult) -> dict[str, Any]:
    return {
        "status": model.status,
        "reason": model.reason,
        # How well it did when tested on a period it was not trained on.
        "validation": dict(model.metrics) if model.available else None,
    }


def _prediction_details(snapshot: a.Snapshot, preds: pr.Predictions) -> dict[str, Any]:
    details: dict[str, Any] = {"models": {"churn": _model_summary(preds.churn)}}
    if preds.churn.available:
        levels = {level: 0 for level in a.INACTIVITY_LEVELS}
        for c in snapshot.customers:
            probability = preds.churn_probability.get(c.customer_id)
            if probability is not None:
                levels[pr.risk_level_from_probability(probability)] += 1
        at_risk = sorted(
            snapshot.customers,
            key=lambda c: preds.churn_probability.get(c.customer_id, 0.0) * c.revenue_12m,
            reverse=True,
        )[:TOP_CUSTOMERS]
        details["churn"] = {
            "averageChurnRiskPct": _r(pr.churn_kpi(snapshot, preds), 1),
            "customersByRiskLevel": levels,
            "highestExpectedRevenueLoss": [
                {
                    "customerId": c.customer_id,
                    "churnProbabilityPct": round(preds.churn_probability.get(c.customer_id, 0.0) * 100, 1),
                    "spendLast12Months": round(c.revenue_12m, 2),
                    "daysSinceLastOrder": c.recency_days,
                }
                for c in at_risk
            ],
        }
    return details


def _r(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def build_context(snapshot: a.Snapshot) -> dict[str, Any]:
    preds = pr.get_predictions(snapshot)
    values, deltas = a.kpis(snapshot)
    values["churnRisk"] = pr.churn_kpi(snapshot, preds)
    growth = a.growth_score(snapshot, values, deltas)
    values["growthScore"] = growth["score"] if growth else None
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
        "segments": [{k: _r(v) if isinstance(v, float) else v for k, v in s.items()} for s in a.segment_summaries(snapshot)],
        "monthlyRevenue": a.monthly_revenue(snapshot)[-RECENT_MONTHS:],
        "revenueDriversLast12Months": {
            "byCategory": drivers["byCategory"][:TOP_ROWS],
            "byCountry": drivers["byCountry"][:TOP_ROWS],
        },
        "newVsReturningLast90Days": drivers["newVsReturning"],
        "revenueAtRiskLast12Months": a.revenue_at_risk(snapshot),
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
        "predictions": _prediction_details(snapshot, preds),
        "definitions": DEFINITIONS,
        "growthScoreBreakdown": growth["components"] if growth else None,
        "notAvailable": _not_available(preds, growth),
    }
