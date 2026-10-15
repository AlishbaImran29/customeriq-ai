"""Response shapes for the analytics endpoints (camelCase, matching lib/types.ts).

Prediction fields (churn probability, predicted CLV, forecast) are null unless the
corresponding model passed its quality gate (see services/predictions.py);
`meta.models` says which are available, with validation metrics or the reason
they are not. The growth score is always null (no agreed formula).
"""

from datetime import date
from typing import Literal

from app.schemas.imports import CamelModel

SegmentName = Literal[
    "Champions", "Loyal Customers", "Potential Loyalists", "At-Risk Customers", "Lost Customers"
]
RiskLevel = Literal["Low", "Medium", "High", "Critical"]

MODEL_NOT_TRAINED = "Needs a trained and validated model."


class Unavailable(CamelModel):
    field: str
    reason: str


class Metric(CamelModel):
    label: str
    value: str


class ModelInfo(CamelModel):
    """Whether a prediction model is available, and how well it was tested."""

    status: Literal["available", "unavailable"]
    reason: str | None
    metrics: list[Metric]


class ModelsMeta(CamelModel):
    churn: ModelInfo
    clv: ModelInfo
    forecast: ModelInfo


class Meta(CamelModel):
    """Common context: data date, model status, and which values are not available."""

    source: Literal["live"] = "live"
    as_of: date | None
    customer_count: int
    segmented: bool
    models: ModelsMeta
    unavailable: list[Unavailable]


class HealthFactors(CamelModel):
    purchase_frequency: float
    spending_behavior: float
    engagement: float | None
    activity_trend: float


class CustomerOut(CamelModel):
    id: str
    name: str
    email: str
    channel: str | None
    segment: SegmentName | None
    orders: int
    revenue: float
    current_clv: float
    predicted_clv: float | None = None
    churn_probability: float | None = None
    # Rule-based inactivity level (days since last order ÷ usual gap), not a prediction.
    risk_level: RiskLevel
    health_score: int
    health_factors: HealthFactors
    engagement_missing: bool
    last_purchase: date
    days_since_last_order: int
    recommended_action: str


class Kpis(CamelModel):
    total_customers: float | None
    revenue: float | None
    average_clv: float | None
    retention_rate: float | None
    churn_risk: float | None
    growth_score: float | None


class SegmentStats(CamelModel):
    name: SegmentName
    customers: int
    revenue: float
    avg_clv: float
    avg_predicted_clv: float | None


class RevenuePoint(CamelModel):
    """Actual months have `actual`; forecast months have `forecast` and `range`."""

    month: str
    actual: float | None = None
    forecast: float | None = None
    range: tuple[float, float] | None = None
    partial: bool = False


class ShareRow(CamelModel):
    name: str
    revenue: float
    share: float
    # Only set for category/channel/country groups (not for new-vs-returning).
    orders: int | None = None
    customers: int | None = None
    avg_order_value: float | None = None
    repeat_rate: float | None = None


class RevenueDrivers(CamelModel):
    by_category: list[ShareRow]
    by_channel: list[ShareRow]
    by_country: list[ShareRow]
    new_vs_returning: list[ShareRow]


class AtRiskRow(CamelModel):
    segment: SegmentName
    customers: int
    at_risk: float


class RecommendationOut(CamelModel):
    id: str
    category: Literal["Retention Campaign", "Upsell", "Cross-Sell", "Customer Recovery"]
    title: str
    detail: str
    impact: Literal["High", "Medium", "Low"]
    target_segment: SegmentName
    audience_size: int
    estimated_revenue: float | None
    historical_revenue: float
    next_action: str


class ExecutiveSummary(CamelModel):
    headline: str
    bullets: list[str]
    method: Literal["rules"]


class HealthBucket(CamelModel):
    range: str
    label: str
    customers: int


class RiskBucket(CamelModel):
    level: RiskLevel
    customers: int


class GrowthComponent(CamelModel):
    key: str
    label: str
    measure: str        # the measured value, e.g. "+12.3%"
    value: int          # its 0-100 sub-score
    weight: int         # percent weight after re-scaling for missing inputs


class GrowthScoreDetails(CamelModel):
    """How the Growth Score was calculated (our own composite, not an industry standard)."""

    score: int
    components: list[GrowthComponent]
    missing: list[str]


class OverviewOut(CamelModel):
    meta: Meta
    kpis: Kpis
    kpi_deltas: Kpis
    growth_score_details: GrowthScoreDetails | None
    executive_summary: ExecutiveSummary
    revenue_series: list[RevenuePoint]
    segments: list[SegmentStats]
    top_recommendations: list[RecommendationOut]
    at_risk_customers: list[CustomerOut]


class CustomersOut(CamelModel):
    meta: Meta
    total: int
    customers: list[CustomerOut]


class CohortRow(CamelModel):
    label: str
    size: int
    # % of the cohort that ordered in month 0, 1, 2...; null where that month is not measurable yet.
    retention: list[float | None]


class CohortsOut(CamelModel):
    meta: Meta
    cohorts: list[CohortRow]
    averages: list[float | None]
    months: int
    # The month still in progress (left out of the comparison), if any.
    partial_month: str | None


class SegmentsOut(CamelModel):
    meta: Meta
    segments: list[SegmentStats]


class ChurnOut(CamelModel):
    meta: Meta
    churn_rate: float | None
    churn_rate_delta: float | None
    distribution: list[RiskBucket]
    customers: list[CustomerOut]


class ClvOut(CamelModel):
    meta: Meta
    average_clv: float | None
    average_predicted_clv: float | None
    segments: list[SegmentStats]
    customers: list[CustomerOut]


class HealthOut(CamelModel):
    meta: Meta
    weights: dict[str, float]
    weights_without_engagement: dict[str, float]
    distribution: list[HealthBucket]
    customers: list[CustomerOut]


class RevenueOut(CamelModel):
    meta: Meta
    series: list[RevenuePoint]
    at_risk_by_segment: list[AtRiskRow]
    drivers: RevenueDrivers


class RecommendationsOut(CamelModel):
    meta: Meta
    items: list[RecommendationOut]
