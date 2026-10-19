"""Turn a return probability into a risk level and a plain action for the seller.

The thresholds and the action texts live in `order_risk_config.py`. Levels are only handed out
when the trust rule allowed the model (see `order_risk_model.py`); otherwise there is nothing
to assess and no number is shown.
"""

import math
from dataclasses import dataclass

from app.services import order_risk_config as config
from app.services.order_features import OrderInput
from app.services.order_risk_model import OrderRiskResult, score_orders

LEVELS = ("Low", "Medium", "High")


@dataclass(frozen=True)
class OrderAssessment:
    order_id: str
    probability: float   # 0-1, the model's estimate (not a fact)
    level: str           # "Low" | "Medium" | "High"
    action: str


def risk_level(probability: float) -> str:
    """Low below RISK_LOW_BELOW, High above RISK_HIGH_ABOVE, Medium in between."""
    if math.isnan(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("A probability must be a number from 0 to 1.")
    if probability < config.RISK_LOW_BELOW:
        return "Low"
    if probability > config.RISK_HIGH_ABOVE:
        return "High"
    return "Medium"


def action_for(level: str) -> str:
    return config.RISK_ACTIONS[level]


def assess_orders(result: OrderRiskResult, orders: list[OrderInput]) -> dict[str, OrderAssessment]:
    """Level and action for every order, or {} when the model is not available."""
    return {
        order_id: OrderAssessment(order_id, p, level := risk_level(p), action_for(level))
        for order_id, p in score_orders(result, orders).items()
    }
