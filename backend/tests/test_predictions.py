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
    pr._cache = None
    yield
    pr._cache = None


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
    _, y, ids = pr._dataset(hists, date(2026, 2, 1), 90, "churn")
    labels = dict(zip(ids, y, strict=True))
    assert labels == {"STAYS": 0.0, "LEAVES": 1.0}  # LEAVES' next order is outside 90 days
    _, spend, ids = pr._dataset(hists, date(2026, 2, 1), 90, "spend")
    assert dict(zip(ids, spend, strict=True)) == {"STAYS": 50.0, "LEAVES": 0.0}


# --- quality gates ---------------------------------------------------------------------------

def test_empty_data_is_unavailable():
    preds = pr.train_all(a.build_snapshot([]))
    assert {m.status for m in (preds.churn, preds.clv, preds.forecast)} == {"unavailable"}
    assert preds.churn_probability == {} and preds.forecast_points == []


def test_short_history_is_unavailable_with_reason():
    facts = [fact(f"C{i}", date(2026, 9, 1) + timedelta(days=i % 30)) for i in range(60)]
    preds = pr.train_all(a.build_snapshot(facts))
    assert preds.churn.reason.startswith("Not enough history")
    assert preds.clv.reason.startswith("Not enough history")
    assert preds.forecast.reason.startswith("Not enough history")
    assert preds.churn_probability == {} and preds.predicted_spend == {}


def test_too_few_customers_is_unavailable():
    # Plenty of history, but only 40 customers: below the 200 needed to learn from.
    facts = [fact(f"C{i}", date(2025, 1, 1) + timedelta(days=30 * k + i)) for i in range(40) for k in range(20)]
    preds = pr.train_all(a.build_snapshot(facts))
    assert preds.churn.status == "unavailable" and "needs at least 200" in preds.churn.reason
    assert preds.clv.status == "unavailable"


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

    # CLV is gated on beating the repeat-last-6-months baseline; either outcome is consistent.
    assert preds.clv.available == bool(preds.predicted_spend)
    assert all(v >= 0 for v in preds.predicted_spend.values())


# --- revenue forecast -----------------------------------------------------------------------------

def monthly_orders(values: list[float], last_day: date) -> list[a.OrderFact]:
    """One order per month (day 28) with the given values; the last order is on `last_day`."""
    facts = []
    year, month = last_day.year, last_day.month
    start = year * 12 + month - 1 - (len(values) - 1)
    for k, value in enumerate(values):
        y, m = divmod(start + k, 12)
        day = last_day if k == len(values) - 1 else date(y, m + 1, 28)
        facts.append(fact(f"M{k}", day, value))
    return facts


def test_forecast_follows_a_clear_trend_with_an_uncertainty_range():
    values = [1000 + 300 * k + (60 if k % 2 else -60) for k in range(18)]
    snapshot = a.build_snapshot(monthly_orders(values, date(2026, 10, 31)))
    preds = pr.train_all(snapshot)
    assert preds.forecast.available, preds.forecast.reason
    assert [p["month"] for p in preds.forecast_points] == ["Nov 2026", "Dec 2026", "Jan 2027"]
    first = preds.forecast_points[0]
    assert first["forecast"] == pytest.approx(1000 + 300 * 18, rel=0.08)
    for point in preds.forecast_points:
        assert point["range"][0] <= point["forecast"] <= point["range"][1]
    assert preds.forecast_points[2]["forecast"] > preds.forecast_points[0]["forecast"]


def test_forecast_skips_the_unfinished_current_month():
    values = [1000 + 300 * k + (60 if k % 2 else -60) for k in range(18)]
    snapshot = a.build_snapshot(monthly_orders(values, date(2026, 10, 15)))  # mid-month -> partial
    assert a.monthly_revenue(snapshot)[-1]["partial"]
    preds = pr.train_all(snapshot)
    assert preds.forecast.available, preds.forecast.reason
    assert [p["month"] for p in preds.forecast_points] == ["Nov 2026", "Dec 2026", "Jan 2027"]
    # Trend is anchored on the last complete month (Sep): Nov is two steps after it.
    assert preds.forecast_points[0]["forecast"] == pytest.approx(1000 + 300 * 18, rel=0.1)


def test_forecast_needs_twelve_complete_months():
    snapshot = a.build_snapshot(monthly_orders([1000 + 100 * k for k in range(10)], date(2026, 10, 31)))
    assert "at least 12 complete months" in pr.train_all(snapshot).forecast.reason


def test_forecast_is_rejected_when_no_better_than_repeating_the_average():
    # Rising, then flat: a straight trend overshoots the flat final months.
    values = [1000 + 500 * k for k in range(15)] + [8000, 8000, 8000]
    snapshot = a.build_snapshot(monthly_orders(values, date(2026, 10, 31)))
    forecast = pr.train_all(snapshot).forecast
    assert forecast.status == "unavailable"
    assert "no better than repeating the recent average" in forecast.reason


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
    assert overview["kpis"]["growthScore"] is None  # still no agreed formula
    assert "growthScore" in {u["field"] for u in overview["meta"]["unavailable"]}


# --- AI assistant context ----------------------------------------------------------------------------------

def test_assistant_context_has_estimates_with_validation_and_no_personal_data():
    import json

    from app.services.assistant_context import build_context

    ctx = build_context(a.build_snapshot(synthetic_facts(800)))
    churn = ctx["predictions"]["models"]["churn"]
    assert churn["status"] == "available"
    assert "Accuracy on unseen period (AUC)" in churn["validation"]
    assert ctx["predictions"]["churn"]["highestExpectedRevenueLoss"]
    assert not any(item.startswith("churn probability") for item in ctx["notAvailable"])
    assert any(item.startswith("growth score") for item in ctx["notAvailable"])
    assert "@example.com" not in json.dumps(ctx, default=str)


def test_assistant_context_lists_unavailable_models_with_reasons():
    from app.services.assistant_context import build_context

    facts = [fact(f"C{i}", date(2026, 9, 1) + timedelta(days=i % 30)) for i in range(60)]
    ctx = build_context(a.build_snapshot(facts))
    assert ctx["predictions"]["models"]["churn"]["status"] == "unavailable"
    assert "churn" not in ctx["predictions"]
    assert any(item.startswith("churn probability (Not enough history") for item in ctx["notAvailable"])


# --- regression: found with the real public dataset ----------------------------------------------------------

def test_data_with_no_engagement_at_all_still_trains():
    """Shopify exports (and the public dataset) have no engagement column. An all-empty feature
    used to crash the boosting library and break every dashboard page."""
    facts = [
        a.OrderFact(f.customer_id, f.name, f.email, f.order_date, f.value, f.channel, f.category, f.country, None)
        for f in synthetic_facts(800)
    ]
    preds = pr.train_all(a.build_snapshot(facts))
    for model in (preds.churn, preds.clv, preds.forecast):
        # Each model either trains or is declined by its quality gate; none may crash.
        assert "could not be trained" not in (model.reason or ""), model.reason
    assert preds.clv.available, preds.clv.reason
    assert all(v >= 0 for v in preds.predicted_spend.values())
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
    assert preds.clv.status in ("available", "unavailable")  # the other models are unaffected
