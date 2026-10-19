"""Response shape of GET /order-risk (camelCase, matching frontend/lib/types.ts)."""

from datetime import date
from typing import Literal

from app.schemas.analytics import Meta
from app.schemas.imports import CamelModel

OrderRiskLevel = Literal["Low", "Medium", "High"]


class ReasonOut(CamelModel):
    """A "Why?" reason: an English template with {placeholders}, the values, and the finished text."""

    template: str
    params: dict[str, str]
    text: str


class OrderRiskRowOut(CamelModel):
    order_id: str
    order_date: date
    customer_id: str
    customer_name: str
    amount: float                    # in the currency of the imported data
    probability: float               # 0-1: the model's estimate, not a fact
    level: OrderRiskLevel
    action: str
    reasons: list[ReasonOut]
    whatsapp_phone: str | None       # international digits for the wa.me link; None = no usable number


class OrderRiskModelOut(CamelModel):
    """The trust rule's decision and the evidence behind it. Present whether or not the model is shown."""

    status: Literal["available", "unavailable"]
    reason: str | None
    metric: str
    model_score: float | None
    baseline_score: float | None
    model_precision_top: float | None
    baseline_precision_top: float | None
    top_fraction: float
    split_date: date | None
    train_end: date | None
    as_of: date | None
    maturity_days: int
    train_rows: int
    test_rows: int
    test_return_rate: float | None
    label_source: str | None
    low_below: float
    high_above: float


class SavingsCountsOut(CamelModel):
    """Counts from the test period. The page multiplies flagged_returned by the shipping cost."""

    flagged_levels: list[str]
    test_start: date
    test_end: date
    test_orders: int
    flagged_orders: int
    flagged_returned: int
    false_alarms: int
    total_returned: int


class OrderRiskOut(CamelModel):
    meta: Meta
    model: OrderRiskModelOut
    window_days: int
    window_start: date | None
    window_orders: int               # orders in the recent window (all levels)
    level_counts: dict[str, int]     # Low / Medium / High, over the whole window
    orders: list[OrderRiskRowOut]    # the risky ones first, at most `limit`
    truncated: bool
    savings_high: SavingsCountsOut | None
    savings_medium_high: SavingsCountsOut | None
