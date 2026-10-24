"""The "Why?" of a churn prediction: the top reasons a customer's risk is high, in plain language.

The churn model is a gradient-boosted tree model, so it has no coefficients to read. Instead each reason is measured
by replacing ONE input with the typical (median) value of all customers and asking the model again: if the predicted
risk drops by a clear amount, that input was pushing this customer's risk up. The three biggest pushes become the reasons.
Nothing is made up: a reason appears only if removing it really changed the model's answer.

Like the Order Risk reasons, a reason is a TEMPLATE plus PARAMETERS, never a finished sentence, so the page can translate the
template and fill in the numbers. Every template is listed in TEMPLATES and a test checks that each has an Urdu translation.
"""

from __future__ import annotations

import numpy as np

MAX_REASONS = 3
MIN_DROP = 0.02  # a reason must move the predicted risk by at least 2 percentage points

# feature -> (template when the customer is ABOVE the typical value, template when BELOW). {value} is the customer's own number.
_TEXT: dict[str, tuple[str, str]] = {
    "recency_days": ("No order for {value} days", "Last order was {value} days ago"),
    "orders": ("{value} orders so far", "Only {value} orders so far"),
    "orders_90d": ("{value} orders in the last 90 days", "Only {value} orders in the last 90 days"),
    "orders_180d": ("{value} orders in the last 180 days", "Only {value} orders in the last 180 days"),
    "spend_total": ("Total spend is higher than most customers", "Total spend is lower than most customers"),
    "spend_90d": ("Spent more than most customers in the last 90 days", "Spent less than most customers in the last 90 days"),
    "spend_180d": ("Spent more than most customers in the last 180 days", "Spent less than most customers in the last 180 days"),
    "avg_order_value": ("Average order is bigger than most customers'", "Average order is smaller than most customers'"),
    "typical_gap_days": ("Usually waits {value} days between orders", "Usually orders every {value} days"),
    "activity_ratio": ("Silent for {value}x the usual gap between orders", "Still inside the usual gap between orders"),
    "tenure_days": ("Has been a customer for {value} days", "Has been a customer for only {value} days"),
    "engagement": ("High engagement score", "Low engagement score"),
}

TEMPLATES = tuple(t for pair in _TEXT.values() for t in pair)

# Shown as whole numbers, except the ratio.
_RATIO = {"activity_ratio"}


def _format(feature: str, value: float) -> str:
    return f"{value:.1f}" if feature in _RATIO else f"{round(value):,}"


def explain(estimator, x_now: np.ndarray, medians: np.ndarray, features: list[str]) -> dict[int, list[dict]]:
    """For every row of `x_now`: up to MAX_REASONS dicts {feature, drop, value, above}, strongest first.

    `estimator.predict(x)` must return risk between 0 and 1 for the full feature matrix."""
    base = estimator.predict(x_now)
    drops = np.zeros_like(x_now)
    for k in range(x_now.shape[1]):
        changed = x_now.copy()
        changed[:, k] = medians[k]
        drops[:, k] = base - estimator.predict(changed)  # positive = this input raises the customer's risk
    result: dict[int, list[dict]] = {}
    for i in range(x_now.shape[0]):
        order = np.argsort(-drops[i])
        picked = []
        for k in order[:MAX_REASONS]:
            value = x_now[i, k]
            if drops[i, k] < MIN_DROP or np.isnan(value) or np.isnan(medians[k]):
                continue
            picked.append({"feature": features[k], "drop": float(drops[i, k]), "value": float(value), "above": bool(value > medians[k])})
        result[i] = picked
    return result


def as_reasons(items: list[dict]) -> list[dict]:
    """[{template, params, text}] ready for the page: the English template, its values, and the finished English text."""
    out = []
    for item in items:
        above_text, below_text = _TEXT[item["feature"]]
        template = above_text if item["above"] else below_text
        params = {"value": _format(item["feature"], item["value"])}
        out.append({"template": template, "params": params, "text": template.replace("{value}", params["value"])})
    return out
