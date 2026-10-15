"""Customer-intelligence endpoints. Values are computed from imported orders.

Prediction fields come from trained models (services/predictions.py) and are
null unless the model passed its quality gate; `meta.models` explains why.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analytics import (
    MODEL_NOT_TRAINED,
    ChurnOut,
    ClvOut,
    CohortsOut,
    CustomerOut,
    CustomersOut,
    HealthOut,
    Kpis,
    Meta,
    Metric,
    ModelInfo,
    ModelsMeta,
    OverviewOut,
    RecommendationsOut,
    RevenueOut,
    SegmentsOut,
    Unavailable,
)
from app.services import analytics as a
from app.services import predictions as pr
from app.services.analytics_data import load_snapshot

router = APIRouter(tags=["analytics"])

DEFAULT_LIMIT = 500
MAX_PERIOD_DAYS = 1095  # three years
MAX_LIMIT = 2000

# Which trained model produces each prediction field.
_FIELD_MODEL = {
    "churnProbability": "churn",
    "churnRisk": "churn",
    "predictedClv": "clv",
    "revenueForecast": "forecast",
}
GROWTH_SCORE_REASON = (
    "Needs at least three of its four inputs; revenue and customer growth need 180+ days of order history."
)


def _model_info(model: pr.ModelResult) -> ModelInfo:
    return ModelInfo(
        status=model.status,
        reason=model.reason,
        metrics=[Metric(label=label, value=value) for label, value in model.metrics],
    )


def _meta(snapshot: a.Snapshot, preds: pr.Predictions, *fields: str, growth: dict | None = None) -> Meta:
    """Response context. `fields` are prediction fields this page would show; those
    whose model is not available are listed with the reason."""
    unavailable = []
    for field in fields:
        if field == "growthScore":
            if growth is None:
                unavailable.append(Unavailable(field=field, reason=GROWTH_SCORE_REASON))
            continue
        model: pr.ModelResult = getattr(preds, _FIELD_MODEL[field])
        if not model.available:
            unavailable.append(Unavailable(field=field, reason=model.reason or MODEL_NOT_TRAINED))
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
        models=ModelsMeta(
            churn=_model_info(preds.churn),
            clv=_model_info(preds.clv),
            forecast=_model_info(preds.forecast),
        ),
        unavailable=unavailable,
    )


def _churn_probability(c: a.CustomerMetrics, preds: pr.Predictions) -> float | None:
    return preds.churn_probability.get(c.customer_id) if preds.churn.available else None


def _predicted_spend(c: a.CustomerMetrics, preds: pr.Predictions) -> float | None:
    return preds.predicted_spend.get(c.customer_id) if preds.clv.available else None


def _customer(c: a.CustomerMetrics, preds: pr.Predictions) -> CustomerOut:
    probability = _churn_probability(c, preds)
    spend = _predicted_spend(c, preds)
    return CustomerOut(
        id=c.customer_id,
        name=c.name,
        email=c.email,
        channel=c.channel,
        segment=c.segment,
        orders=c.orders,
        revenue=round(c.revenue, 2),
        current_clv=round(c.revenue, 2),
        predicted_clv=None if spend is None else round(c.revenue + spend, 2),
        churn_probability=None if probability is None else round(probability * 100, 1),
        # With a churn model the level comes from the probability; otherwise it is the
        # rule-based inactivity level (days since last order ÷ usual gap).
        risk_level=pr.risk_level_from_probability(probability) if probability is not None else c.inactivity_level,
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


def _customers(items: list[a.CustomerMetrics], limit: int, preds: pr.Predictions) -> list[CustomerOut]:
    return [_customer(c, preds) for c in items[:limit]]


def _churn_order(snapshot: a.Snapshot, preds: pr.Predictions) -> list[a.CustomerMetrics]:
    """Most at-risk first: by predicted probability, else by inactivity ratio."""
    if preds.churn.available:
        return sorted(snapshot.customers, key=lambda c: _churn_probability(c, preds) or 0.0, reverse=True)
    return sorted(snapshot.customers, key=lambda c: c.activity_ratio, reverse=True)


def _risk_distribution(snapshot: a.Snapshot, preds: pr.Predictions) -> list[dict]:
    if not preds.churn.available:
        return a.inactivity_distribution(snapshot)
    counts = dict.fromkeys(a.INACTIVITY_LEVELS, 0)
    for c in snapshot.customers:
        probability = _churn_probability(c, preds)
        if probability is not None:
            counts[pr.risk_level_from_probability(probability)] += 1
    return [{"level": level, "customers": counts[level]} for level in a.INACTIVITY_LEVELS]


def _revenue_series(snapshot: a.Snapshot, preds: pr.Predictions) -> list[dict]:
    """Actual months, plus forecast months when the forecast model is available. The
    last complete month also carries the forecast so the chart lines connect."""
    series: list[dict] = a.monthly_revenue(snapshot)
    if not preds.forecast.available or not preds.forecast_points:
        return series
    last_complete = max(i for i, p in enumerate(series) if not p["partial"])
    anchor = series[last_complete]["actual"]
    series[last_complete] = {**series[last_complete], "forecast": anchor, "range": [anchor, anchor]}
    return series + preds.forecast_points


@router.get("/dashboard/overview", response_model=OverviewOut)
def overview(
    start: date | None = Query(None, description="First day of the KPI period (with `end`)."),
    end: date | None = Query(None, description="Last day of the KPI period; later than the data is cut back."),
    days: int = Query(a.WINDOW_DAYS, ge=1, le=MAX_PERIOD_DAYS, description="Period length when `start` is not given."),
    db: Session = Depends(get_db),
) -> OverviewOut:
    snapshot = load_snapshot(db)
    preds = pr.get_predictions(snapshot)
    if snapshot.as_of is not None:
        end = min(end, snapshot.as_of) if end else snapshot.as_of
        if start is not None:
            if start > end:
                raise HTTPException(status_code=422, detail="The start date must be on or before the end date.")
            days = (end - start).days + 1
            if days > MAX_PERIOD_DAYS:
                raise HTTPException(status_code=422, detail=f"Choose a period of at most {MAX_PERIOD_DAYS} days.")
    values, deltas = a.kpis(snapshot, days, end)
    values["churnRisk"] = pr.churn_kpi(snapshot, preds)
    growth = a.growth_score(snapshot, values, deltas, days)
    values["growthScore"] = growth["score"] if growth else None
    if preds.churn.available:
        # Biggest expected revenue loss first: predicted chance of leaving x 12-month spend.
        attention = sorted(
            snapshot.customers,
            key=lambda c: (_churn_probability(c, preds) or 0.0) * c.revenue_12m,
            reverse=True,
        )
    elif snapshot.segmented:
        attention = sorted(
            (c for c in snapshot.customers if c.segment == "At-Risk Customers"),
            key=lambda c: c.revenue_12m,
            reverse=True,
        )
    else:
        attention = sorted(snapshot.customers, key=lambda c: c.activity_ratio, reverse=True)
    recs = a.recommendations(snapshot)
    return OverviewOut(
        meta=_meta(snapshot, preds, "churnRisk", "growthScore", "revenueForecast", growth=growth),
        kpis=Kpis.model_validate(values),
        kpi_deltas=Kpis.model_validate(deltas),
        growth_score_details=growth,
        executive_summary=a.executive_summary(snapshot, values, deltas, days, end),
        revenue_series=_revenue_series(snapshot, preds),
        segments=a.segment_summaries(snapshot, preds.predicted_spend if preds.clv.available else None),
        top_recommendations=[r for r in recs if r["impact"] == "High"][:3] or recs[:3],
        at_risk_customers=_customers(attention, 4, preds),
    )


@router.get("/customers", response_model=CustomersOut)
def customers(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT), db: Session = Depends(get_db)
) -> CustomersOut:
    snapshot = load_snapshot(db)
    preds = pr.get_predictions(snapshot)
    ranked = sorted(snapshot.customers, key=lambda c: c.revenue, reverse=True)
    return CustomersOut(
        meta=_meta(snapshot, preds, "churnProbability", "predictedClv"),
        total=len(ranked),
        customers=_customers(ranked, limit, preds),
    )


@router.get("/cohorts", response_model=CohortsOut)
def cohorts(db: Session = Depends(get_db)) -> CohortsOut:
    """Monthly cohort retention. Pure counting, so no prediction model is trained for it."""
    snapshot = load_snapshot(db)
    not_used = ModelInfo(status="unavailable", reason="Not used on this page.", metrics=[])
    meta = Meta(
        as_of=snapshot.as_of,
        customer_count=len(snapshot.customers),
        segmented=snapshot.segmented,
        models=ModelsMeta(churn=not_used, clv=not_used, forecast=not_used),
        unavailable=[],
    )
    return CohortsOut(meta=meta, **a.cohort_retention(snapshot))


@router.get("/segments", response_model=SegmentsOut)
def segments(db: Session = Depends(get_db)) -> SegmentsOut:
    snapshot = load_snapshot(db)
    preds = pr.get_predictions(snapshot)
    return SegmentsOut(
        meta=_meta(snapshot, preds, "predictedClv"),
        segments=a.segment_summaries(snapshot, preds.predicted_spend if preds.clv.available else None),
    )


@router.get("/predictions/churn", response_model=ChurnOut)
def churn(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT), db: Session = Depends(get_db)
) -> ChurnOut:
    """Churn probability when the model passed its quality gate; otherwise rule-based
    inactivity levels (see `meta.models.churn`)."""
    snapshot = load_snapshot(db)
    preds = pr.get_predictions(snapshot)
    return ChurnOut(
        meta=_meta(snapshot, preds, "churnProbability", "churnRisk"),
        churn_rate=pr.churn_kpi(snapshot, preds),
        churn_rate_delta=None,
        distribution=_risk_distribution(snapshot, preds),
        customers=_customers(_churn_order(snapshot, preds), limit, preds),
    )


@router.get("/predictions/clv", response_model=ClvOut)
def clv(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT), db: Session = Depends(get_db)
) -> ClvOut:
    """Current (historical) CLV, plus predicted CLV when its model passed the quality gate."""
    snapshot = load_snapshot(db)
    preds = pr.get_predictions(snapshot)
    values, _ = a.kpis(snapshot)
    average_predicted = None
    if preds.clv.available and snapshot.customers:
        average_predicted = sum(
            c.revenue + (_predicted_spend(c, preds) or 0.0) for c in snapshot.customers
        ) / len(snapshot.customers)
    ranked = sorted(snapshot.customers, key=lambda c: c.revenue, reverse=True)
    return ClvOut(
        meta=_meta(snapshot, preds, "predictedClv"),
        average_clv=values["averageClv"],
        average_predicted_clv=average_predicted,
        segments=a.segment_summaries(snapshot, preds.predicted_spend if preds.clv.available else None),
        customers=_customers(ranked, limit, preds),
    )


@router.get("/customers/health", response_model=HealthOut)
def health_scores(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT), db: Session = Depends(get_db)
) -> HealthOut:
    snapshot = load_snapshot(db)
    preds = pr.get_predictions(snapshot)
    ranked = sorted(snapshot.customers, key=lambda c: c.health_score)
    return HealthOut(
        meta=_meta(snapshot, preds),
        weights=a.HEALTH_WEIGHTS,
        weights_without_engagement=a.HEALTH_WEIGHTS_WITHOUT_ENGAGEMENT,
        distribution=a.health_distribution(snapshot),
        customers=_customers(ranked, limit, preds),
    )


@router.get("/revenue/intelligence", response_model=RevenueOut)
def revenue(db: Session = Depends(get_db)) -> RevenueOut:
    snapshot = load_snapshot(db)
    preds = pr.get_predictions(snapshot)
    return RevenueOut(
        meta=_meta(snapshot, preds, "revenueForecast"),
        series=_revenue_series(snapshot, preds),
        at_risk_by_segment=a.revenue_at_risk(snapshot),
        drivers=a.revenue_drivers(snapshot),
    )


@router.get("/recommendations", response_model=RecommendationsOut)
def recommendations(db: Session = Depends(get_db)) -> RecommendationsOut:
    snapshot = load_snapshot(db)
    return RecommendationsOut(
        meta=_meta(snapshot, pr.get_predictions(snapshot)), items=a.recommendations(snapshot)
    )
