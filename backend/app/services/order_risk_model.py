"""Order Risk Check: train a simple model and decide whether it may be shown.

The core rule of CustomerIQ AI applies here: a prediction is shown ONLY if the model beats a
simple baseline on orders it has not seen. Otherwise the result says "unavailable" and gives
the reason plus both scores. Nothing is invented.

How it works, in order:
1. Labels. 1 = the order was returned / cancelled, 0 = it was not. Only orders whose label is
   complete are used: orders newer than LABEL_MATURITY_DAYS may still be cancelled later.
2. Split by TIME, never at random. The newest 25% of the labelled orders are the TEST set. The
   model trains on older orders, with a gap before the test period (see order_risk_config.py),
   and its training labels are "what the seller knew on the split date".
3. Model: Logistic Regression on the features from `order_features.py`. It is simple and
   explainable: each feature has one coefficient (used later for the "Why?" reasons).
4. Baseline: the customer's own past cancel rate. A new customer gets the overall rate of the
   training period.
5. Compare on the test set with ROC-AUC and with precision among the riskiest 10% of orders.
6. Decide with the trust rule. Save both scores either way.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.models.order import OUTCOME_RETURNED
from app.services.order_features import (
    NUMERIC_FEATURES,
    OrderFeatures,
    OrderInput,
    build_order_features,
    label,
)
from app.services.order_risk_config import (
    LABEL_MATURITY_DAYS,
    MAX_COUNTRIES,
    MIN_AUC_MARGIN,
    MIN_CLASS_ROWS,
    MIN_MODEL_AUC,
    MIN_TRAIN_ROWS,
    TEST_FRACTION,
    TOP_FRACTION,
    TRAIN_TEST_GAP_DAYS,
)

ModelStatus = Literal["available", "unavailable"]
METRIC = "ROC-AUC"

# Features that are long-tailed counts or days: a log scale stops a few huge values from
# dominating. The ratio of the order value to the customer's average is capped first.
_LOG_FEATURES = {
    "past_orders", "days_since_previous_order", "item_count", "distinct_products", "address_length",
}
_RATIO_CAP = 20.0


@dataclass
class OrderRiskResult:
    status: ModelStatus
    reason: str | None = None
    metric: str = METRIC
    label_source: str | None = None
    model_auc: float | None = None
    baseline_auc: float | None = None
    model_precision_top: float | None = None       # share really returned among the riskiest 10%
    baseline_precision_top: float | None = None
    top_fraction: float = TOP_FRACTION
    split_date: date | None = None                 # first day of the test period
    train_end: date | None = None                  # last day of the training period
    as_of: date | None = None                      # the latest order in the data
    maturity_days: int = LABEL_MATURITY_DAYS
    train_rows: int = 0
    test_rows: int = 0
    test_return_rate: float | None = None
    # What was learned (only when available); not part of the saved record.
    pipeline: Pipeline | None = field(default=None, repr=False)
    countries: list[str] = field(default_factory=list, repr=False)
    feature_names: list[str] = field(default_factory=list, repr=False)

    @property
    def available(self) -> bool:
        return self.status == "available"


# --- measuring ------------------------------------------------------------------------

def precision_at_top(scores: np.ndarray, labels: np.ndarray, fraction: float) -> float:
    """Among the riskiest `fraction` of orders, the share that really were returned.

    Orders with exactly the same score are not ranked by an arbitrary order: the tied group
    that straddles the cut contributes its average, so the result does not depend on how the
    rows happen to be sorted (a baseline gives many equal scores)."""
    n = len(scores)
    k = max(1, math.ceil(fraction * n))
    order = np.sort(scores)[::-1]
    cut = order[k - 1]
    above = scores > cut
    tied = scores == cut
    take_from_tied = k - int(above.sum())
    hits = labels[above].sum() + labels[tied].mean() * take_from_tied
    return float(hits / k)


# --- features -> numbers ----------------------------------------------------------------

def _top_countries(features: list[OrderFeatures]) -> list[str]:
    counts = Counter(f.country for f in features if f.country)
    return [name for name, _ in counts.most_common(MAX_COUNTRIES)]


def _matrix(features: list[OrderFeatures], countries: list[str]) -> np.ndarray:
    """One row per order: the numeric features (NaN = missing) then one column per country."""
    log_columns = [i for i, name in enumerate(NUMERIC_FEATURES) if name in _LOG_FEATURES]
    ratio_column = NUMERIC_FEATURES.index("value_vs_customer_avg")
    rows = []
    for f in features:
        row = f.numeric_row()
        for i in log_columns:
            row[i] = math.log1p(row[i])               # log1p(NaN) stays NaN
        row[ratio_column] = math.log1p(min(row[ratio_column], _RATIO_CAP))
        row.extend(1.0 if f.country == c else 0.0 for c in countries)
        rows.append(row)
    return np.array(rows, dtype=float)


def _new_pipeline() -> Pipeline:
    return Pipeline([
        # Missing values are filled with the median AND flagged by an extra 0/1 column, so the
        # model can still learn that "unknown" itself means something. A column with no value at all
        # (e.g. no address data yet) is kept as a constant, so the columns never change shape.
        ("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
        ("scale", StandardScaler()),
        ("model", LogisticRegression(max_iter=1000)),
    ])


# --- training -------------------------------------------------------------------------

def _unavailable(reason: str, **info) -> OrderRiskResult:
    return OrderRiskResult(status="unavailable", reason=reason, **info)


def _label_source(orders: list[OrderInput]) -> str | None:
    sources = {o.label_source for o in orders if o.label_source}
    if not sources:
        return None
    return next(iter(sources)) if len(sources) == 1 else "mixed: " + " + ".join(sorted(sources))


def orders_tested_on(result: OrderRiskResult, orders: list[OrderInput]) -> list[OrderInput]:
    """The orders the model was TESTED on: complete label, on or after the split date.

    These are the only orders a savings estimate may use, because the model never saw them
    while learning. [] when the model has no test period (not enough data)."""
    if result.split_date is None or result.as_of is None:
        return []
    mature_until = result.as_of - timedelta(days=result.maturity_days)
    return [
        o for o in orders
        if label(o) is not None and result.split_date <= o.order_date <= mature_until
    ]


def train_order_risk(orders: list[OrderInput]) -> OrderRiskResult:
    """Train on older orders, test on newer ones, and apply the trust rule."""
    if not orders:
        return _unavailable("No orders have been imported yet.")
    as_of = max(o.order_date for o in orders)
    mature_until = as_of - timedelta(days=LABEL_MATURITY_DAYS)
    # Complete labels only: a known outcome, and old enough to have been cancelled by now.
    labelled = sorted(
        (o for o in orders if label(o) is not None and o.order_date <= mature_until),
        key=lambda o: (o.order_date, o.order_id),
    )
    info = {"as_of": as_of, "label_source": _label_source(labelled)}
    if len(labelled) < MIN_TRAIN_ROWS + MIN_CLASS_ROWS * 2:
        return _unavailable(
            f"Only {len(labelled)} orders have a complete outcome (known, and older than "
            f"{LABEL_MATURITY_DAYS} days). More history with delivered/returned results is needed.",
            **info,
        )

    split_date = labelled[int(len(labelled) * (1 - TEST_FRACTION))].order_date
    train_end = split_date - timedelta(days=TRAIN_TEST_GAP_DAYS)
    train = [o for o in labelled if o.order_date <= train_end]
    test = [o for o in labelled if o.order_date >= split_date]
    info.update(split_date=split_date, train_end=train_end, train_rows=len(train), test_rows=len(test))

    # Training labels as the seller knew them on the split date: a return reported AFTER that
    # day did not exist yet, so such an order still looked "not returned".
    y_train = np.array(
        [int(o.outcome == OUTCOME_RETURNED and o.outcome_date is not None and o.outcome_date < split_date)
         for o in train]
    )
    y_test = np.array([label(o) for o in test])  # the final truth for the test orders
    info["test_return_rate"] = float(y_test.mean()) if len(y_test) else None

    problems = _data_problems(train, y_train, y_test)
    if problems:
        return _unavailable(problems, **info)

    features = build_order_features(orders)  # every order sees only its own customer's EARLIER orders
    f_train = [features[o.order_id] for o in train]
    f_test = [features[o.order_id] for o in test]
    countries = _top_countries(f_train)

    pipeline = _new_pipeline().fit(_matrix(f_train, countries), y_train)
    model_scores = pipeline.predict_proba(_matrix(f_test, countries))[:, 1]

    # Baseline: the customer's own past cancel rate; a new customer gets the overall training rate.
    overall = float(y_train.mean())
    baseline_scores = np.array(
        [overall if f.past_cancel_rate is None else f.past_cancel_rate for f in f_test]
    )

    model_auc = float(roc_auc_score(y_test, model_scores))
    baseline_auc = float(roc_auc_score(y_test, baseline_scores))
    model_top = precision_at_top(model_scores, y_test, TOP_FRACTION)
    baseline_top = precision_at_top(baseline_scores, y_test, TOP_FRACTION)
    scores = dict(
        model_auc=model_auc, baseline_auc=baseline_auc,
        model_precision_top=model_top, baseline_precision_top=baseline_top,
    )

    failures = _trust_failures(model_auc, baseline_auc, model_top, baseline_top)
    if failures:
        return _unavailable(" ".join(failures), **info, **scores)
    return OrderRiskResult(
        status="available",
        pipeline=pipeline,
        countries=countries,
        feature_names=list(
            pipeline.named_steps["impute"].get_feature_names_out(list(NUMERIC_FEATURES) + [f"country={c}" for c in countries])
        ),
        **info,
        **scores,
    )


def _data_problems(train: list[OrderInput], y_train: np.ndarray, y_test: np.ndarray) -> str | None:
    """Why there is not enough data to train and test fairly, or None."""
    if len(train) < MIN_TRAIN_ROWS:
        return (
            f"Only {len(train)} orders are old enough to train on (need {MIN_TRAIN_ROWS}). "
            "More order history is needed."
        )
    for name, y in (("training", y_train), ("test", y_test)):
        positives = int(y.sum())
        negatives = len(y) - positives
        if min(positives, negatives) < MIN_CLASS_ROWS:
            return (
                f"The {name} period has only {positives} returned and {negatives} not-returned orders "
                f"(need at least {MIN_CLASS_ROWS} of each)."
            )
    return None


def _trust_failures(model_auc: float, baseline_auc: float, model_top: float, baseline_top: float) -> list[str]:
    """The trust rule. An empty list means the model may be shown."""
    scores = (
        f"{METRIC}: model {model_auc:.3f}, baseline {baseline_auc:.3f}. "
        f"Riskiest {TOP_FRACTION:.0%}: model {model_top:.1%} returned, baseline {baseline_top:.1%}."
    )
    failures = []
    if model_auc < MIN_MODEL_AUC:
        failures.append(f"The model's {METRIC} is below {MIN_MODEL_AUC:.2f}, too close to guessing.")
    if model_auc < baseline_auc + MIN_AUC_MARGIN:
        failures.append(
            f"The model does not beat the baseline (the customer's own past cancel rate) by at least "
            f"{MIN_AUC_MARGIN:.2f} {METRIC}."
        )
    if model_top <= baseline_top:
        failures.append("Among the riskiest orders the model is not more accurate than the baseline.")
    return [*failures, scores] if failures else []


# --- using a trained model ---------------------------------------------------------------

def score_orders(result: OrderRiskResult, orders: list[OrderInput]) -> dict[str, float]:
    """Return-probability for every order (0-1), or {} when the model is not available."""
    if not result.available or result.pipeline is None:
        return {}
    features = build_order_features(orders)
    ids = list(features)
    probabilities = result.pipeline.predict_proba(_matrix([features[i] for i in ids], result.countries))[:, 1]
    return dict(zip(ids, (float(p) for p in probabilities), strict=True))


def contributions(result: OrderRiskResult, features: list[OrderFeatures]) -> tuple[np.ndarray, np.ndarray]:
    """How much each input pushed each order's risk up (+) or down (-), in log-odds.

    For a logistic regression this is exact and simple: contribution = coefficient x the
    standardised value, and the contributions plus the intercept add up to the model's log-odds.
    "0" means "exactly average", so a positive number is a reason the order is riskier than a
    typical one. Columns follow `result.feature_names`. Also returns the standardised values
    (above 0 = higher than usual), which tell the direction of each input."""
    if not result.available or result.pipeline is None:
        raise ValueError("Reasons exist only for an available model.")
    imputed = result.pipeline.named_steps["impute"].transform(_matrix(features, result.countries))
    scaled = result.pipeline.named_steps["scale"].transform(imputed)
    return scaled * result.pipeline.named_steps["model"].coef_[0], scaled
