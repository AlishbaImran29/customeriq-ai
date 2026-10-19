"""The "Why?" reasons: they come from the model, are true statements, and can be translated."""

import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.services.order_features import OrderInput, build_order_features
from app.services.order_risk_config import MAX_REASONS, MIN_REASON_WEIGHT
from app.services.order_risk_model import contributions, train_order_risk
from app.services.order_risk_reasons import TEMPLATES, explain_orders
from tests.test_order_risk_model import make_orders


@pytest.fixture(scope="module")
def trained():
    orders = make_orders(signal=True)
    return orders, train_order_risk(orders)


def test_no_reasons_without_a_trusted_model():
    orders = make_orders(signal=False)
    assert explain_orders(train_order_risk(orders), orders) == {}


def test_reasons_are_few_ordered_and_strong_enough(trained):
    orders, result = trained
    explained = explain_orders(result, orders)
    assert set(explained) == {o.order_id for o in orders}
    for reasons in explained.values():
        assert len(reasons) <= MAX_REASONS
        weights = [r.weight for r in reasons]
        assert weights == sorted(weights, reverse=True) and all(w >= MIN_REASON_WEIGHT for w in weights)
        assert len({r.template for r in reasons}) == len(reasons)    # a reason is never shown twice


def test_the_reason_for_a_big_order_is_the_item_count_and_a_small_order_has_none(trained):
    """In the made-up data big orders are the ones that get returned, so the model must say so."""
    orders, result = trained
    big = next(o for o in orders if o.item_count == 30)
    small = next(o for o in orders if o.item_count == 1)
    explained = explain_orders(result, orders, {big.order_id, small.order_id})
    assert any(r.code == "item_count" and r.params == {"count": "30"} for r in explained[big.order_id])
    assert all(r.code != "item_count" for r in explained[small.order_id])
    assert "Number of items: 30 (more than usual)" in [r.text for r in explained[big.order_id]]


def habit_orders(seed: int = 3) -> list[OrderInput]:
    """Made-up history where some customers return most of what they buy and others almost
    nothing, so a customer's own past is a real signal. Very large orders are also often
    returned, a second signal that the past alone cannot show (so the model can beat the baseline)."""
    rng = random.Random(seed)
    orders = []
    for c in range(300):
        chance = 0.6 if c % 3 == 0 else 0.05
        for k in range(14):
            placed = date(2024, 1, 1) + timedelta(days=rng.randrange(0, 730))
            items = rng.choice([1, 2, 3, 30])
            returned = rng.random() < (max(chance, 0.7) if items == 30 else chance)
            orders.append(OrderInput(
                f"H{c}-{k}", f"HC{c}", placed, 40.0, item_count=items,
                outcome="returned" if returned else "delivered",
                outcome_date=placed + timedelta(days=rng.randrange(1, 10)) if returned else None,
            ))
    return orders


def test_a_return_history_reason_states_the_true_counts():
    # One customer returned 2 of their first 3 orders (known in time), then orders again.
    mine = [
        OrderInput("M1", "ME", date(2024, 1, 5), 50.0, item_count=2, outcome="returned", outcome_date=date(2024, 1, 9)),
        OrderInput("M2", "ME", date(2024, 2, 5), 50.0, item_count=2, outcome="returned", outcome_date=date(2024, 2, 9)),
        OrderInput("M3", "ME", date(2024, 3, 5), 50.0, item_count=2, outcome="delivered"),
        OrderInput("M4", "ME", date(2024, 4, 5), 50.0, item_count=2),
    ]
    orders = habit_orders() + mine
    result = train_order_risk(orders)
    assert result.available
    reasons = explain_orders(result, orders, {"M4"})["M4"]
    history = [r for r in reasons if r.code == "past_cancel_rate"]
    assert history and history[0].params == {"returned": "2", "total": "3"}
    assert history[0].text == "Returned 2 of 3 earlier orders"


def test_a_new_customer_reason_appears_only_once(trained):
    orders, result = trained
    features = build_order_features(orders)
    newcomers = {order_id for order_id, f in features.items() if f.is_new_customer}
    for reasons in explain_orders(result, orders, newcomers).values():
        assert sum(r.template.startswith("New customer") for r in reasons) <= 1


def test_contributions_explain_the_models_own_score(trained):
    """Sanity check of the maths: intercept + the contributions = the model's log-odds."""
    import numpy as np

    orders, result = trained
    features = list(build_order_features(orders).values())[:50]
    pushes, _ = contributions(result, features)
    model = result.pipeline.named_steps["model"]
    from app.services.order_risk_model import _matrix

    expected = result.pipeline.decision_function(_matrix(features, result.countries))
    assert np.allclose(pushes.sum(axis=1) + model.intercept_[0], expected)


def test_every_template_has_an_urdu_translation():
    """A reason is translated by looking up its English template, so a missing entry would
    leave that reason in English. The frontend table must hold every template."""
    table = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "i18n.ts"
    if not table.exists():
        pytest.skip("frontend folder not available")
    text = table.read_text(encoding="utf-8")
    missing = [t for t in TEMPLATES if f'"{t}":' not in text]
    assert missing == []
    # ... and the translation keeps the same {placeholders}.
    for template in TEMPLATES:
        line = next(l for l in text.splitlines() if l.strip().startswith(f'"{template}":'))
        translated = line.split(f'"{template}":', 1)[1]
        assert sorted(re.findall(r"\{(\w+)\}", template)) == sorted(re.findall(r"\{(\w+)\}", translated)), template
