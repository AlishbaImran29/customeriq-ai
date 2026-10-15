"""Customer-intelligence endpoints. Values are computed from imported orders."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analytics import (
    MODEL_NOT_TRAINED,
    ChurnOut,
    ClvOut,
    CustomerOut,
    CustomersOut,
    HealthOut,
    Kpis,
    Meta,
    OverviewOut,
    RecommendationsOut,
    RevenueOut,
    SegmentsOut,
    Unavailable,
)
from app.services import analytics as a
from app.services.analytics_data import load_snapshot

router = APIRouter(tags=["analytics"])

DEFAULT_LIMIT = 500
MAX_LIMIT = 2000

_PREDICTIONS = {
    "churnProbability": MODEL_NOT_TRAINED,
    "predictedClv": MODEL_NOT_TRAINED,
    "revenueForecast": MODEL_NOT_TRAINED,
    "churnRisk": MODEL_NOT_TRAINED,
    "growthScore": "No agreed formula yet; needs a defined and validated model.",
}


def _meta(snapshot: a.Snapshot, *fields: str) -> Meta:
    unavailable = [Unavailable(field=f, reason=_PREDICTIONS[f]) for f in fields]
    if not snapshot.empty and not snapshot.segmented:
        unavailable.append(
            Unavailable(
                field="segments",
                reason=f"Segmentation needs at least {a.MIN_CUSTOMERS_FOR_SEGMENTS} customers.",
            )
        )
    return Meta(
        as_of=snapshot.as_of,
        customer_count=len(snapshot.customers),
        segmented=snapshot.segmented,
        unavailable=unavailable,
    )


def _customer(c: a.CustomerMetrics) -> CustomerOut:
    return CustomerOut(
        id=c.customer_id,
        name=c.name,
        email=c.email,
        channel=c.channel,
        segment=c.segment,
        orders=c.orders,
        revenue=round(c.revenue, 2),
        current_clv=round(c.revenue, 2),
        risk_level=c.inactivity_level,
        health_score=c.health_score,
        health_factors={
            "purchase_frequency": round(c.frequency_factor),
            "spending_behavior": round(c.spending_factor),
            "engagement": round(c.engagement) if c.engagement is not None else None,
            "activity_trend": round(c.activity_trend),
        },
        engagement_missing=c.engagement_missing,
        last_purchase=c.last_order,
        days_since_last_order=c.recency_days,
        recommended_action=c.recommended_action,
    )


def _customers(items: list[a.CustomerMetrics], limit: int) -> list[CustomerOut]:
    return [_customer(c) for c in items[:limit]]


@router.get("/dashboard/overview", response_model=OverviewOut)
def overview(db: Session = Depends(get_db)) -> OverviewOut:
    snapshot = load_snapshot(db)
    values, deltas = a.kpis(snapshot)
    if snapshot.segmented:
        attention = sorted(
            (c for c in snapshot.customers if c.segment == "At-Risk Customers"),
            key=lambda c: c.revenue_12m,
            reverse=True,
        )
    else:
        attention = sorted(snapshot.customers, key=lambda c: c.activity_ratio, reverse=True)
    recs = a.recommendations(snapshot)
    return OverviewOut(
        meta=_meta(snapshot, "churnRisk", "growthScore", "revenueForecast"),
        kpis=Kpis.model_validate(values),
        kpi_deltas=Kpis.model_validate(deltas),
        executive_summary=a.executive_summary(snapshot, values, deltas),
        revenue_series=a.monthly_revenue(snapshot),
        segments=a.segment_summaries(snapshot),
        top_recommendations=[r for r in recs if r["impact"] == "High"][:3] or recs[:3],
        at_risk_customers=_customers(attention, 4),
    )


@router.get("/customers", response_model=CustomersOut)
def customers(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT), db: Session = Depends(get_db)
) -> CustomersOut:
    snapshot = load_snapshot(db)
    ranked = sorted(snapshot.customers, key=lambda c: c.revenue, reverse=True)
    return CustomersOut(
        meta=_meta(snapshot, "churnProbability", "predictedClv"),
        total=len(ranked),
        customers=_customers(ranked, limit),
    )


@router.get("/segments", response_model=SegmentsOut)
def segments(db: Session = Depends(get_db)) -> SegmentsOut:
    snapshot = load_snapshot(db)
    return SegmentsOut(
        meta=_meta(snapshot, "predictedClv"), segments=a.segment_summaries(snapshot)
    )


@router.get("/predictions/churn", response_model=ChurnOut)
def churn(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT), db: Session = Depends(get_db)
) -> ChurnOut:
    """Churn probability is not available yet; returns rule-based inactivity levels."""
    snapshot = load_snapshot(db)
    ranked = sorted(snapshot.customers, key=lambda c: c.activity_ratio, reverse=True)
    return ChurnOut(
        meta=_meta(snapshot, "churnProbability", "churnRisk"),
        churn_rate=None,
        churn_rate_delta=None,
        distribution=a.inactivity_distribution(snapshot),
        customers=_customers(ranked, limit),
    )


@router.get("/predictions/clv", response_model=ClvOut)
def clv(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT), db: Session = Depends(get_db)
) -> ClvOut:
    """Current (historical) CLV only; predicted CLV is not available yet."""
    snapshot = load_snapshot(db)
    values, _ = a.kpis(snapshot)
    ranked = sorted(snapshot.customers, key=lambda c: c.revenue, reverse=True)
    return ClvOut(
        meta=_meta(snapshot, "predictedClv"),
        average_clv=values["averageClv"],
        average_predicted_clv=None,
        segments=a.segment_summaries(snapshot),
        customers=_customers(ranked, limit),
    )


@router.get("/customers/health", response_model=HealthOut)
def health_scores(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT), db: Session = Depends(get_db)
) -> HealthOut:
    snapshot = load_snapshot(db)
    ranked = sorted(snapshot.customers, key=lambda c: c.health_score)
    return HealthOut(
        meta=_meta(snapshot),
        weights=a.HEALTH_WEIGHTS,
        weights_without_engagement=a.HEALTH_WEIGHTS_WITHOUT_ENGAGEMENT,
        distribution=a.health_distribution(snapshot),
        customers=_customers(ranked, limit),
    )


@router.get("/revenue/intelligence", response_model=RevenueOut)
def revenue(db: Session = Depends(get_db)) -> RevenueOut:
    snapshot = load_snapshot(db)
    return RevenueOut(
        meta=_meta(snapshot, "revenueForecast"),
        series=a.monthly_revenue(snapshot),
        at_risk_by_segment=a.revenue_at_risk(snapshot),
        drivers=a.revenue_drivers(snapshot),
    )


@router.get("/recommendations", response_model=RecommendationsOut)
def recommendations(db: Session = Depends(get_db)) -> RecommendationsOut:
    snapshot = load_snapshot(db)
    return RecommendationsOut(meta=_meta(snapshot), items=a.recommendations(snapshot))
