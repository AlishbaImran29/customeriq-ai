"""Order Risk model: the measuring helpers, the time split, and above all the trust rule."""

import random
from datetime import date, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import select

from app.models import OrderRiskRun
from app.services.order_features import OrderInput
from app.services.order_risk_config import LABEL_MATURITY_DAYS, MIN_AUC_MARGIN, TRAIN_TEST_GAP_DAYS
from app.services.order_risk_model import precision_at_top, score_orders, train_order_risk
from app.services.order_risk_runs import latest_run, save_run
from tests.conftest import requires_database

START = date(2024, 1, 1)


def make_orders(signal: bool, customers: int = 300, per_customer: int = 14, seed: int = 7) -> list[OrderInput]:
    """Made-up shop history over ~2 years. With `signal`, big orders are far more often returned
    (a fact known BEFORE shipping, which the customer's past cannot reveal); without it, returns
    are pure chance and no model can predict them."""
    rng = random.Random(seed)
    orders = []
    for c in range(customers):
        for k in range(per_customer):
            placed = START + timedelta(days=rng.randrange(0, 730))
            items = rng.choice([1, 2, 3, 5, 8, 20, 30])
            chance = (0.55 if items >= 20 else 0.08) if signal else 0.2
            returned = rng.random() < chance
            orders.append(OrderInput(
                order_id=f"O{c}-{k}", customer_id=f"C{c}", order_date=placed, value=10.0 * items,
                ordered_at=datetime.combine(placed, datetime.min.time()) + timedelta(hours=rng.randrange(8, 22)),
                item_count=items, distinct_products=min(items, 3), country="UK",
                outcome="returned" if returned else "delivered",
                outcome_date=placed + timedelta(days=rng.randrange(1, 10)) if returned else None,
                label_source="proxy: cancellations",
            ))
    return orders


# --- measuring ------------------------------------------------------------------------

def test_precision_at_top_counts_the_riskiest_share():
    scores = np.array([0.9, 0.8, 0.7, 0.2, 0.1, 0.05, 0.04, 0.03, 0.02, 0.01])
    labels = np.array([1, 0, 1, 0, 0, 0, 0, 0, 0, 0])
    assert precision_at_top(scores, labels, 0.2) == 0.5      # top 2 orders: one returned
    assert precision_at_top(scores, labels, 0.3) == pytest.approx(2 / 3)


def test_precision_at_top_does_not_depend_on_the_order_of_tied_scores():
    # Eight orders share the top score, only the first two cases return: a fair answer is 25%.
    scores = np.array([1.0] * 8 + [0.0, 0.0])
    labels = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 0])
    assert precision_at_top(scores, labels, 0.2) == pytest.approx(0.25)
    assert precision_at_top(scores[::-1], labels[::-1], 0.2) == pytest.approx(0.25)


# --- the trust rule -------------------------------------------------------------------

def test_a_model_that_beats_the_baseline_is_available():
    result = train_order_risk(make_orders(signal=True))
    assert result.available and result.reason is None
    assert result.model_auc >= result.baseline_auc + MIN_AUC_MARGIN
    assert result.model_precision_top > result.baseline_precision_top
    assert result.label_source == "proxy: cancellations"


def test_a_model_that_cannot_beat_the_baseline_is_hidden_but_its_scores_are_kept():
    result = train_order_risk(make_orders(signal=False))
    assert not result.available
    # Not available means: no model is kept, but BOTH scores and the reason are reported.
    assert result.pipeline is None
    assert result.model_auc is not None and result.baseline_auc is not None
    assert "baseline" in result.reason and "ROC-AUC" in result.reason


def test_unavailable_models_score_nothing():
    orders = make_orders(signal=False)
    assert score_orders(train_order_risk(orders), orders) == {}


def test_available_model_scores_every_order_between_0_and_1():
    orders = make_orders(signal=True)
    scores = score_orders(train_order_risk(orders), orders)
    assert set(scores) == {o.order_id for o in orders}
    assert all(0.0 <= p <= 1.0 for p in scores.values())


def test_too_little_data_is_reported_with_a_reason():
    assert "No orders" in train_order_risk([]).reason
    few = train_order_risk(make_orders(signal=True, customers=3, per_customer=4))
    assert not few.available and "complete outcome" in few.reason


def test_orders_without_an_outcome_are_never_used():
    orders = [o for o in make_orders(signal=True)]
    unknown = [OrderInput(**{**o.__dict__, "outcome": None, "outcome_date": None}) for o in orders]
    result = train_order_risk(unknown)
    assert not result.available and "complete outcome" in result.reason


# --- time split and label maturity ----------------------------------------------------------

def test_the_test_period_is_later_than_the_training_period_with_a_gap():
    result = train_order_risk(make_orders(signal=True))
    assert result.train_end < result.split_date
    assert (result.split_date - result.train_end).days == TRAIN_TEST_GAP_DAYS


def test_orders_too_new_to_have_a_final_label_are_left_out():
    orders = make_orders(signal=True)
    latest = max(o.order_date for o in orders)
    result = train_order_risk(orders)
    mature = sum(1 for o in orders if o.order_date <= latest - timedelta(days=LABEL_MATURITY_DAYS))
    assert result.train_rows + result.test_rows < mature     # the gap also drops some
    assert result.as_of == latest and result.maturity_days == LABEL_MATURITY_DAYS


def test_new_orders_with_the_wrong_label_cannot_change_the_result():
    """Orders inside the maturity window (labels still incomplete) are ignored, so even
    deliberately wrong labels there change nothing."""
    orders = make_orders(signal=True)
    latest = max(o.order_date for o in orders)
    cutoff = latest - timedelta(days=LABEL_MATURITY_DAYS)
    flipped = [
        OrderInput(**{**o.__dict__, "outcome": "returned", "outcome_date": o.order_date + timedelta(days=1)})
        if o.order_date > cutoff else o
        for o in orders
    ]
    a, b = train_order_risk(orders), train_order_risk(flipped)
    assert (a.model_auc, a.baseline_auc) == (b.model_auc, b.baseline_auc)


# --- saving the decision ----------------------------------------------------------------

@requires_database
def test_every_run_is_saved_with_its_scores_and_decision(db_session):
    good = save_run(db_session, train_order_risk(make_orders(signal=True)))
    bad = save_run(db_session, train_order_risk(make_orders(signal=False)))
    rows = {r.id: r for r in db_session.scalars(select(OrderRiskRun))}
    assert rows[good.id].decision == "available" and rows[good.id].metric == "ROC-AUC"
    assert rows[good.id].model_score > rows[good.id].baseline_score
    assert rows[good.id].split_date is not None and rows[good.id].label_source == "proxy: cancellations"
    assert rows[bad.id].decision == "unavailable" and rows[bad.id].reason
    assert rows[bad.id].model_score is not None and rows[bad.id].baseline_score is not None
    assert latest_run(db_session).id == bad.id
