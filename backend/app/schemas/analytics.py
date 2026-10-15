"""Response shapes for the analytics endpoints (camelCase, matching lib/types.ts).

Fields that need a trained model (churn probability, predicted CLV, forecasts,
growth score) are always null until Phase 4 and come with an `unavailable` note.
"""

from datetime import date
from typing import Literal

from app.schemas.imports import CamelModel

SegmentName = Literal[
    "Champions", "Loyal Customers", "Potential Loyalists", "At-Risk Customers", "Lost Customers"
]
RiskLevel = Literal["Low", "Medium", "High", "Critical"]

MODEL_NOT_TRAINED = "Needs a trained and validated model (planned for Phase 4)."


class Unavailable(CamelModel):
    field: str
    reason: str


class Meta(CamelModel):
    """Common context: data date and which values are not available."""

    source: Literal["live"] = "live"
    as_of: date | None
    customer_count: int
    segmented: bool
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
    month: str
    actual: float
    partial: bool


class ShareRow(CamelModel):
    name: str
    revenue: float
    share: float


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


class OverviewOut(CamelModel):
    meta: Meta
    kpis: Kpis
    kpi_deltas: Kpis
    executive_summary: ExecutiveSummary
    revenue_series: list[RevenuePoint]
    segments: list[SegmentStats]
    top_recommendations: list[RecommendationOut]
    at_risk_customers: list[CustomerOut]


class CustomersOut(CamelModel):
    meta: Meta
    total: int
    customers: list[CustomerOut]


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
    forecast: None = None
    at_risk_by_segment: list[AtRiskRow]
    drivers: RevenueDrivers


class RecommendationsOut(CamelModel):
    meta: Meta
    items: list[RecommendationOut]
