"""Prediction models: no look-ahead, honest gates, retraining. Made-up data only."""

import csv
import importlib.util
import io
import math
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.services import analytics as a
from app.services import predictions as pr
from tests.conftest import requires_database

_spec = importlib.util.spec_from_file_location(
    "generate_demo_data",
    Path(__file__).resolve().parents[1] / "scripts" / "generate_demo_data.py",
)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


@pytest.fixture(autouse=True)
def fresh_cache():
    pr._cache.clear()
    yield
    pr._cache.clear()


def fact(customer: str, day: date, value: float = 50.0, engagement: float | None = None) -> a.OrderFact:
    return a.OrderFact(customer, customer, f"{customer.lower()}@example.com", day, Decimal(str(value)),
                       "Shopify", "Skincare", "US", None if engagement is None else Decimal(str(engagement)))


def synthetic_facts(customers: int) -> list[a.OrderFact]:
    rows = gen.generate(random.Random(7)) if customers == gen.CUSTOMERS else None
    if rows is None:
        original, gen.CUSTOMERS = gen.CUSTOMERS, customers
        try:
            rows = gen.generate(random.Random(7))
        finally:
            gen.CUSTOMERS = original
    return [
        fact(r["customer_id"], date.fromisoformat(r["order_date"]), float(r["order_value"]),
             float(r["engagement"]) if r["engagement"] else None)
        for r in rows
    ]


# --- point-in-time features: no look-ahead ---------------------------------------------

def hist_from(facts: list[a.OrderFact]) -> pr._Hist:
    return pr._histories(a.build_snapshot(facts))[facts[0].customer_id]


def test_features_ignore_orders_after_the_cutoff():
    cutoff = date(2026, 6, 1)
    base = [fact("A", date(2026, 3, 1), 100), fact("A", date(2026, 5, 1), 50)]
    later = base + [fact("A", date(2026, 7, 1), 9999), fact("A", date(2026, 8, 1), 9999)]
    assert pr._features(hist_from(base), cutoff) == pr._features(hist_from(later), cutoff)


def test_feature_values():
    h = hist_from([fact("A", date(2026, 3, 1), 100), fact("A", date(2026, 5, 1), 50, 80),
                   fact("A", date(2026, 5, 1), 10, 60)])
    f = dict(zip(pr.FEATURES, pr._features(h, date(2026, 6, 1)), strict=True))
    assert f["recency_days"] == 31 and f["orders"] == 3
    assert f["spend_total"] == 160 and f["avg_order_value"] == pytest.approx(160 / 3)
    assert f["typical_gap_days"] == 61  # distinct order dates: Mar 1 -> May 1
    assert f["engagement"] == 70        # mean of the values that exist
    assert pr._features(h, date(2026, 2, 1)) is None  # nothing before the first order


def test_missing_engagement_stays_missing_not_zero():
    h = hist_from([fact("A", date(2026, 3, 1)), fact("A", date(2026, 5, 1))])
    value = dict(zip(pr.FEATURES, pr._features(h, date(2026, 6, 1)), strict=True))["engagement"]
    assert math.isnan(value)


def test_churn_label_means_no_order_in_the_next_90_days():
    facts = [
        fact("STAYS", date(2026, 1, 1)), fact("STAYS", date(2026, 3, 1)),
        fact("LEAVES", date(2026, 1, 1)), fact("LEAVES", date(2026, 7, 1)),
    ]
    hists = pr._histories(a.build_snapshot(facts))
    _, y, ids = pr._dataset(hists, date(2026, 2, 1), 90)
    labels = dict(zip(ids, y, strict=True))
    assert labels == {"STAYS": 0.0, "LEAVES": 1.0}  # LEAVES' next order is outside 90 days


# --- quality gates ---------------------------------------------------------------------------

def test_empty_data_is_unavailable():
    preds = pr.train_all(a.build_snapshot([]))
    assert preds.churn.status == "unavailable"
    assert preds.churn_probability == {}


def test_short_history_is_unavailable_with_reason():
    facts = [fact(f"C{i}", date(2026, 9, 1) + timedelta(days=i % 30)) for i in range(60)]
    preds = pr.train_all(a.build_snapshot(facts))
    assert preds.churn.reason.startswith("Not enough data yet")
    assert preds.churn_probability == {}


def test_too_few_customers_is_unavailable():
    # Plenty of history, but only 40 customers: below the 200 needed to learn from.
    facts = [fact(f"C{i}", date(2025, 1, 1) + timedelta(days=30 * k + i)) for i in range(40) for k in range(20)]
    preds = pr.train_all(a.build_snapshot(facts))
    assert preds.churn.status == "unavailable" and "needs at least 200" in preds.churn.reason


# --- full pipeline on a larger made-up dataset --------------------------------------------------

def test_models_train_validate_and_predict():
    snapshot = a.build_snapshot(synthetic_facts(800))
    preds = pr.train_all(snapshot)

    assert preds.churn.available, preds.churn.reason
    metrics = dict(preds.churn.metrics)
    auc, baseline = float(metrics["Accuracy on unseen period (AUC)"]), float(metrics["Simple recency rule (AUC)"])
    assert auc >= pr.MIN_CHURN_AUC and auc > baseline
    assert set(preds.churn_probability) == {c.customer_id for c in snapshot.customers}
    assert all(0.0 <= p <= 1.0 for p in preds.churn_probability.values())
    # Sanity: customers silent for a long time are riskier than very recent buyers.
    by_recency = sorted(snapshot.customers, key=lambda c: c.recency_days)
    recent = [preds.churn_probability[c.customer_id] for c in by_recency[:50]]
    silent = [preds.churn_probability[c.customer_id] for c in by_recency[-50:]]
    assert sum(silent) / 50 > sum(recent) / 50


# --- retraining ----------------------------------------------------------------------------------------

def test_models_are_cached_and_retrained_when_data_changes():
    facts = synthetic_facts(300)
    first = pr.get_predictions(a.build_snapshot(facts))
    assert pr.get_predictions(a.build_snapshot(facts)) is first  # same data -> cached
    changed = pr.get_predictions(a.build_snapshot(facts + [fact("NEW", date(2026, 10, 13), 77)]))
    assert changed is not first                                   # data changed -> retrained
    assert "NEW" in changed.churn_probability or not changed.churn.available


@pytest.mark.parametrize("probability, level", [
    (0.0, "Low"), (0.24, "Low"), (0.25, "Medium"), (0.49, "Medium"),
    (0.5, "High"), (0.79, "High"), (0.8, "Critical"), (1.0, "Critical"),
])
def test_risk_levels_from_probability(probability, level):
    assert pr.risk_level_from_probability(probability) == level


# --- through the API (rolled back) --------------------------------------------------------------------------

@requires_database
def test_api_shows_predictions_only_when_models_are_available(db_client):
    original, gen.CUSTOMERS = gen.CUSTOMERS, 800
    try:
        rows = gen.generate(random.Random(7))
    finally:
        gen.CUSTOMERS = original
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    upload = db_client.post("/api/v1/imports", files={"file": ("big.csv", buffer.getvalue().encode(), "text/csv")})
    assert upload.status_code == 201, upload.text

    body = db_client.get("/api/v1/predictions/churn?limit=5").json()
    models = body["meta"]["models"]
    assert models["churn"]["status"] == "available" and models["churn"]["reason"] is None
    labels = [m["label"] for m in models["churn"]["metrics"]]
    assert "Accuracy on unseen period (AUC)" in labels
    assert "churnProbability" not in {u["field"] for u in body["meta"]["unavailable"]}
    assert body["churnRate"] is not None and 0 <= body["churnRate"] <= 100
    top = body["customers"]
    assert all(c["churnProbability"] is not None for c in top)
    probabilities = [c["churnProbability"] for c in top]
    assert probabilities == sorted(probabilities, reverse=True)

    overview = db_client.get("/api/v1/dashboard/overview").json()
    assert overview["kpis"]["churnRisk"] == pytest.approx(body["churnRate"])
    details = overview["growthScoreDetails"]
    assert overview["kpis"]["growthScore"] == details["score"] and 0 <= details["score"] <= 100
    assert "growthScore" not in {u["field"] for u in overview["meta"]["unavailable"]}


# --- regression: found with the real public dataset ----------------------------------------------------------

def test_data_with_no_engagement_at_all_still_trains():
    """Shopify exports (and the public dataset) have no engagement column. An all-empty feature
    used to crash the boosting library and break every dashboard page."""
    facts = [
        a.OrderFact(f.customer_id, f.name, f.email, f.order_date, f.value, f.channel, f.category, f.country, None)
        for f in synthetic_facts(800)
    ]
    preds = pr.train_all(a.build_snapshot(facts))
    # The model either trains or is declined by its quality gate; it may not crash.
    assert "could not be trained" not in (preds.churn.reason or ""), preds.churn.reason
    # Without engagement, churn may legitimately fall short of the simple recency rule.
    assert preds.churn.available or "Not reliable enough yet" in (preds.churn.reason or "")
    assert all(0.0 <= p <= 1.0 for p in preds.churn_probability.values())


def test_uninformative_features_are_dropped_before_training():
    import numpy as np

    x = np.array([[1.0, 5.0, np.nan, 7.0], [2.0, 5.0, np.nan, 8.0], [3.0, 5.0, np.nan, np.nan]])
    assert pr._usable_columns(x) == [0, 3]  # constant and all-empty columns removed
    with pytest.raises(ValueError):
        pr._fit(pr._classifier(), np.full((4, 3), np.nan), np.array([0, 1, 0, 1]))


def test_a_failing_model_reports_unavailable_instead_of_crashing(monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(pr, "_train_churn", broken)
    preds = pr.train_all(a.build_snapshot(synthetic_facts(300)))
    assert preds.churn.status == "unavailable"
    assert "could not be trained" in preds.churn.reason and preds.churn_probability == {}
