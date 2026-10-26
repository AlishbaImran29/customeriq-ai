"""The trained prediction model: churn probability.

Honesty rules (agreed for Phase 4):
- Every model is trained on an OLDER period and tested on a LATER period it has
  not seen (a time-based split). The measured accuracy is returned with the
  predictions and compared with a simple rule-of-thumb baseline.
- A quality gate decides whether predictions are shown at all. If there is too
  little data, or the model is not better than the baseline, the model reports
  "unavailable" with the reason instead of numbers.
- Missing engagement is left as a missing value (NaN), never treated as zero.
- Models are retrained automatically when the imported data changes (see
  `get_predictions`), so they never go stale.

Definitions (all relative to the latest order date, `as_of`):
- Churn: the customer places NO order in the next 90 days.

Only churn is trained. Predicted lifetime value and a revenue forecast were tried and removed: on the Online Retail II data neither beat its
simple baseline (predicted spend was off by £689 per customer against £620 for "repeat the last 6 months"; the revenue trend was off by 56%
against 39% for "repeat the recent average"), so under the honesty rule they would never have been shown.
"""

from __future__ import annotations

import logging
import math
import warnings
import threading
from bisect import bisect_right
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from statistics import median
from typing import Literal

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score

from app.services import churn_reasons
from app.services.analytics import SINGLE_ORDER_GAP_DAYS, Snapshot

logger = logging.getLogger(__name__)

CHURN_HORIZON_DAYS = 90

# Quality gates.
MIN_TRAIN_ROWS = 200      # customers with history at the training cutoff
MIN_CLASS_ROWS = 30       # churned and retained examples, in training and in testing
MIN_CHURN_AUC = 0.65

FEATURES = [
    "recency_days", "orders", "orders_90d", "orders_180d", "spend_total", "spend_90d",
    "spend_180d", "avg_order_value", "typical_gap_days", "activity_ratio", "tenure_days",
    "engagement",
]
_RECENCY_INDEX = FEATURES.index("recency_days")

ModelStatus = Literal["available", "unavailable"]


# A shortage of data is said the same way everywhere: how many MORE are needed, in the unit the rule
# counts (customers, days or months, not orders: the rules count those).
def _more_days(needed: int, have: int) -> str:
    return f"Not enough data yet: {needed - have} more days of order history needed (you have {have}; it needs at least {needed})."


def _more_customers(needed: int, have: int, days_ago: int) -> str:
    return (
        f"Not enough data yet: {needed - have} more customers with order history needed (only {have} had "
        f"orders {days_ago} days ago; it needs at least {needed})."
    )


@dataclass
class ModelResult:
    status: ModelStatus
    reason: str | None = None
    metrics: list[tuple[str, str]] = field(default_factory=list)
    # The same scores as plain numbers, for the Model Report Card (None when the model never got as far as a test).
    metric: str | None = None
    model_score: float | None = None
    baseline_score: float | None = None
    higher_is_better: bool = True
    test_size: int | None = None
    split_date: date | None = None  # the first day of the test period
    # Churn only: customer id -> the top reasons for that customer's risk (see churn_reasons.py).
    reasons: dict[str, list[dict]] = field(default_factory=dict)

    @classmethod
    def unavailable(cls, reason: str, **scores) -> ModelResult:
        return cls(status="unavailable", reason=reason, **scores)

    @property
    def available(self) -> bool:
        return self.status == "available"


@dataclass
class Predictions:
    churn: ModelResult
    churn_probability: dict[str, float] = field(default_factory=dict)  # 0–1


# --- per-customer history and point-in-time features --------------------------------

@dataclass(frozen=True)
class _Hist:
    dates: list[date]                 # sorted, one entry per order
    values: list[float]
    engagement: list[float | None]
    cum: list[float]                  # cum[k] = sum of the first k order values


def _histories(snapshot: Snapshot) -> dict[str, _Hist]:
    grouped: dict[str, list[tuple[date, float, float | None]]] = defaultdict(list)
    for o in snapshot.orders:
        grouped[o.customer_id].append(
            (o.order_date, float(o.value), None if o.engagement is None else float(o.engagement))
        )
    result = {}
    for customer_id, items in grouped.items():
        items.sort(key=lambda x: x[0])
        values = [i[1] for i in items]
        cum = [0.0]
        for v in values:
            cum.append(cum[-1] + v)
        result[customer_id] = _Hist([i[0] for i in items], values, [i[2] for i in items], cum)
    return result


def _features(h: _Hist, cutoff: date) -> list[float] | None:
    """Features using ONLY orders on or before `cutoff` (no look-ahead)."""
    n = bisect_right(h.dates, cutoff)
    if n == 0:
        return None
    last, first = h.dates[n - 1], h.dates[0]
    distinct = sorted(set(h.dates[:n]))
    gaps = [(b - a).days for a, b in zip(distinct, distinct[1:])]
    typical_gap = max(1.0, float(median(gaps))) if gaps else float(SINGLE_ORDER_GAP_DAYS)
    recency = (cutoff - last).days
    i90 = bisect_right(h.dates, cutoff - timedelta(days=90))
    i180 = bisect_right(h.dates, cutoff - timedelta(days=180))
    engagement = [e for e in h.engagement[:n] if e is not None]
    return [
        float(recency),
        float(n),
        float(n - i90),
        float(n - i180),
        h.cum[n],
        h.cum[n] - h.cum[i90],
        h.cum[n] - h.cum[i180],
        h.cum[n] / n,
        typical_gap,
        recency / typical_gap,
        float((cutoff - first).days),
        sum(engagement) / len(engagement) if engagement else math.nan,  # missing stays missing
    ]


def _dataset(
    hists: dict[str, _Hist], cutoff: date, horizon: int
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Features at `cutoff`; label from the `horizon` days AFTER it."""
    end = cutoff + timedelta(days=horizon)
    rows, labels, ids = [], [], []
    for customer_id, h in hists.items():
        features = _features(h, cutoff)
        if features is None:
            continue
        i, j = bisect_right(h.dates, cutoff), bisect_right(h.dates, end)
        labels.append(float(j == i))                       # 1 = no order in the next `horizon` days
        rows.append(features)
        ids.append(customer_id)
    return np.array(rows, dtype=float).reshape(-1, len(FEATURES)), np.array(labels), ids


@dataclass
class _Fitted:
    """A fitted model plus the feature columns it was trained on."""

    estimator: HistGradientBoostingClassifier | HistGradientBoostingRegressor
    columns: list[int]

    def predict(self, x: np.ndarray) -> np.ndarray:
        if isinstance(self.estimator, HistGradientBoostingClassifier):
            return self.estimator.predict_proba(x[:, self.columns])[:, 1]
        return self.estimator.predict(x[:, self.columns])


def _usable_columns(x: np.ndarray) -> list[int]:
    """Columns with at least two different known values. A constant or entirely empty
    column (for example engagement, when the imported data has none at all) carries no
    information and makes the boosting library fail."""
    return [j for j in range(x.shape[1]) if len(np.unique(x[~np.isnan(x[:, j]), j])) >= 2]


def _fit(estimator, x: np.ndarray, y: np.ndarray) -> _Fitted:
    columns = _usable_columns(x)
    if not columns:
        raise ValueError("no feature has more than one distinct value")
    return _Fitted(estimator.fit(x[:, columns], y), columns)


def _classifier() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=150, learning_rate=0.08, max_depth=3, min_samples_leaf=20,
        l2_regularization=1.0, early_stopping=False, random_state=0,
    )


def _history_days(snapshot: Snapshot) -> int:
    assert snapshot.as_of is not None
    return (snapshot.as_of - min(o.order_date for o in snapshot.orders)).days


# --- churn --------------------------------------------------------------------------

def _train_churn(snapshot: Snapshot, hists: dict[str, _Hist]) -> tuple[ModelResult, dict[str, float]]:
    assert snapshot.as_of is not None
    h = CHURN_HORIZON_DAYS
    need = 2 * h
    if _history_days(snapshot) < need + 90:
        return ModelResult.unavailable(_more_days(need + 90, _history_days(snapshot))), {}
    train_cutoff, test_cutoff = snapshot.as_of - timedelta(days=2 * h), snapshot.as_of - timedelta(days=h)
    x_train, y_train, _ = _dataset(hists, train_cutoff, h)
    x_test, y_test, _ = _dataset(hists, test_cutoff, h)

    if len(y_train) < MIN_TRAIN_ROWS:
        return ModelResult.unavailable(_more_customers(MIN_TRAIN_ROWS, len(y_train), 2 * h)), {}
    problems = _class_problems(y_train, y_test)
    if problems:
        return ModelResult.unavailable("Not reliable enough yet: " + "; ".join(problems) + "."), {}

    model = _fit(_classifier(), x_train, y_train)
    p_test = model.predict(x_test)
    auc = float(roc_auc_score(y_test, p_test))
    baseline_auc = float(roc_auc_score(y_test, x_test[:, _RECENCY_INDEX]))  # longer silence = riskier
    brier = float(brier_score_loss(y_test, p_test))
    scores = dict(metric="ROC-AUC", model_score=auc, baseline_score=baseline_auc, higher_is_better=True, test_size=len(y_test), split_date=test_cutoff)
    if auc < MIN_CHURN_AUC:
        return ModelResult.unavailable(
            f"Not reliable enough yet: accuracy on the test period was {auc:.2f} (AUC), "
            f"below the {MIN_CHURN_AUC:.2f} needed.", **scores
        ), {}
    if auc <= baseline_auc:
        return ModelResult.unavailable(
            f"Not reliable enough yet: the model ({auc:.2f} AUC) was no better than a simple "
            f"'longer since last order = riskier' rule ({baseline_auc:.2f}).", **scores
        ), {}

    # Final model learns from both periods, then scores every customer as of today.
    final = _fit(_classifier(), np.vstack([x_train, x_test]), np.concatenate([y_train, y_test]))
    x_now, _, ids = _dataset(hists, snapshot.as_of, h)
    probabilities = dict(zip(ids, (float(p) for p in final.predict(x_now)), strict=True))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # a column with no values at all (engagement) is fine
        medians = np.nanmedian(np.vstack([x_train, x_test]), axis=0)
    explained = churn_reasons.explain(final, x_now, medians, FEATURES)
    reasons = {customer_id: explained[i] for i, customer_id in enumerate(ids)}
    metrics = [
        ("Accuracy on unseen period (AUC)", f"{auc:.2f}"),
        ("Simple recency rule (AUC)", f"{baseline_auc:.2f}"),
        ("Prediction error (Brier score)", f"{brier:.3f}"),
        ("Tested on", f"the last {h} days of orders, not used for training"),
        ("Trained on", f"{len(y_train) + len(y_test):,} customer snapshots"),
    ]
    return ModelResult("available", None, metrics, reasons=reasons, **scores), probabilities


def _class_problems(y_train: np.ndarray, y_test: np.ndarray) -> list[str]:
    problems = []
    for name, y in (("training", y_train), ("test", y_test)):
        positives = int(y.sum())
        negatives = len(y) - positives
        if min(positives, negatives) < MIN_CLASS_ROWS:
            problems.append(
                f"the {name} period has only {min(positives, negatives)} examples of one outcome "
                f"(needs at least {MIN_CLASS_ROWS})"
            )
    return problems


# --- predicted CLV --------------------------------------------------------------------

def _safely(name: str, train, empty):
    """Run one trainer. An unexpected failure must never break the dashboards: the model
    is reported as unavailable instead, and the details go to the server log."""
    try:
        return train()
    except Exception:
        logger.exception("Training the %s model failed; reporting it as unavailable", name)
        return ModelResult.unavailable(
            "The model could not be trained on this data (details are in the server log)."
        ), empty


def train_all(snapshot: Snapshot) -> Predictions:
    if snapshot.empty:
        none = ModelResult.unavailable("No customer data has been imported yet.")
        return Predictions(churn=none)
    hists = _histories(snapshot)
    churn, probabilities = _safely("churn", lambda: _train_churn(snapshot, hists), {})
    logger.info("Churn model trained: %s (%d customers)", churn.status, len(snapshot.customers))
    return Predictions(churn, probabilities)


def _fingerprint(snapshot: Snapshot) -> tuple:
    return (
        snapshot.as_of,
        len(snapshot.orders),
        len(snapshot.customers),
        round(sum(float(o.value) for o in snapshot.orders), 2),
        sum(o.order_date.toordinal() for o in snapshot.orders),
        round(sum(float(o.engagement) for o in snapshot.orders if o.engagement is not None), 2),
    )


# Models for the last few datasets (the whole business, and each channel the dashboard is filtered to).
_CACHE_SIZE = 8
_cache: OrderedDict[tuple, Predictions] = OrderedDict()
_lock = threading.Lock()


def get_predictions(snapshot: Snapshot) -> Predictions:
    """Models for this data, retrained automatically when the data changes."""
    key = _fingerprint(snapshot)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        predictions = train_all(snapshot)
        _cache[key] = predictions
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
        return predictions


ACTIVE_WINDOW_DAYS = 365


def churn_kpi(snapshot: Snapshot, predictions: Predictions) -> float | None:
    """Average predicted chance (%) of no purchase in the next 90 days among customers who
    ordered in the last 12 months. None when the churn model is not available."""
    if not predictions.churn.available:
        return None
    active = [
        predictions.churn_probability[c.customer_id]
        for c in snapshot.customers
        if c.recency_days <= ACTIVE_WINDOW_DAYS and c.customer_id in predictions.churn_probability
    ]
    return sum(active) / len(active) * 100 if active else None


def risk_level_from_probability(probability: float) -> str:
    """Probability is 0–1."""
    if probability >= 0.8:
        return "Critical"
    if probability >= 0.5:
        return "High"
    if probability >= 0.25:
        return "Medium"
    return "Low"
