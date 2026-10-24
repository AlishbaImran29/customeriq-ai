"""The churn "Why?": reasons come from the model, are few, and every template can be translated. Made-up data only."""

import re
from pathlib import Path

import numpy as np

from app.services import analytics as a
from app.services import churn_reasons as cr
from app.services import predictions as pr
from tests.test_predictions import fresh_cache, synthetic_facts  # noqa: F401  (fresh_cache is an autouse fixture)


class _Model:
    """A stand-in model: risk rises with the first input (recency) only."""

    def predict(self, x):
        return np.clip(x[:, 0] / 100.0, 0, 1)


def test_only_the_input_that_moves_the_prediction_is_a_reason():
    x = np.array([[90.0, 5.0], [10.0, 5.0]])
    out = cr.explain(_Model(), x, np.array([30.0, 5.0]), ["recency_days", "orders"])
    assert [r["feature"] for r in out[0]] == ["recency_days"]       # the second input changes nothing: no reason
    assert out[0][0]["above"] is True and out[0][0]["drop"] > 0.5
    assert out[1] == []                                              # a customer below the typical value has no reason


def test_missing_values_never_become_reasons():
    x = np.array([[90.0, np.nan]])
    out = cr.explain(_Model(), x, np.array([30.0, np.nan]), ["recency_days", "engagement"])
    assert all(r["feature"] != "engagement" for r in out[0])


def test_at_most_three_reasons_and_text_is_filled_in():
    items = [{"feature": f, "drop": 0.3, "value": 12.0, "above": True} for f in ("recency_days", "orders", "orders_90d", "activity_ratio")]
    shown = cr.as_reasons(items[: cr.MAX_REASONS])
    assert len(shown) == 3
    assert shown[0]["text"] == "No order for 12 days"
    assert shown[0]["template"] == "No order for {value} days" and shown[0]["params"] == {"value": "12"}


def test_trained_model_explains_customers_it_scores():
    preds = pr.get_predictions(a.build_snapshot(synthetic_facts(800)))
    assert preds.churn.available, preds.churn.reason
    assert set(preds.churn.reasons) == set(preds.churn_probability)
    assert all(len(v) <= cr.MAX_REASONS for v in preds.churn.reasons.values())
    riskiest = max(preds.churn_probability, key=preds.churn_probability.get)
    assert preds.churn.reasons[riskiest], "the riskiest customer should have at least one reason"
    # The scores for the report card are numbers, not text.
    assert preds.churn.metric == "ROC-AUC" and preds.churn.model_score > preds.churn.baseline_score


def test_every_template_has_an_urdu_translation():
    source = (Path(__file__).resolve().parents[2] / "frontend" / "lib" / "i18n.ts").read_text(encoding="utf-8")
    missing = [t for t in cr.TEMPLATES if f'"{t}":' not in source]
    assert not missing, missing
    assert re.search(r"\{value\}", " ".join(cr.TEMPLATES))
