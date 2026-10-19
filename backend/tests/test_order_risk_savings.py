"""Savings calculator: the arithmetic, the honesty rules, and that only TEST orders are used."""

import math
from datetime import date

import pytest

from app.services.order_features import OrderInput
from app.services.order_risk_levels import OrderAssessment, assess_orders
from app.services.order_risk_model import orders_tested_on, train_order_risk
from app.services.order_risk_savings import check_shipping_cost, count_flagged, savings_estimate
from tests.test_order_risk_model import make_orders


def order(order_id: str, outcome: str) -> OrderInput:
    return OrderInput(order_id, "C", date(2024, 1, 1), 10.0, outcome=outcome)


def assessment(order_id: str, level: str) -> OrderAssessment:
    return OrderAssessment(order_id, 0.5, level, "")


def test_counting_on_a_hand_made_example():
    orders = [order("a", "returned"), order("b", "returned"), order("c", "delivered"),
              order("d", "delivered"), order("e", "returned")]
    levels = {"a": "High", "b": "High", "c": "High", "d": "Low", "e": "Medium"}
    assessed = {k: assessment(k, v) for k, v in levels.items()}
    # Flagged = High: a, b, c. Of those a and b were returned. 3 orders were returned in all.
    assert count_flagged(orders, assessed, ("High",)) == (3, 2, 3)
    assert count_flagged(orders, assessed, ("High", "Medium")) == (4, 3, 3)


@pytest.fixture(scope="module")
def trained():
    orders = make_orders(signal=True)
    return orders, train_order_risk(orders)


def test_estimate_multiplies_returned_flagged_orders_by_the_shipping_cost(trained):
    orders, result = trained
    est = savings_estimate(result, orders, 350.0)
    assert est is not None
    assert est.cost_avoided == est.flagged_returned * 350.0
    assert est.total_return_cost == est.total_returned * 350.0
    assert est.flagged_returned + est.false_alarms == est.flagged_orders
    assert est.flagged_returned <= est.total_returned <= est.test_orders
    assert est.cost_avoided <= est.total_return_cost


def test_the_cost_scales_linearly_and_counts_do_not_depend_on_it(trained):
    orders, result = trained
    a, b = savings_estimate(result, orders, 100.0), savings_estimate(result, orders, 300.0)
    assert (a.flagged_orders, a.flagged_returned) == (b.flagged_orders, b.flagged_returned)
    assert b.cost_avoided == pytest.approx(3 * a.cost_avoided)
    assert savings_estimate(result, orders, 0).cost_avoided == 0


def test_only_orders_the_model_was_tested_on_are_counted(trained):
    orders, result = trained
    tested = orders_tested_on(result, orders)
    assert len(tested) == result.test_rows
    assert all(o.order_date >= result.split_date for o in tested)       # never the training period
    est = savings_estimate(result, orders, 1.0)
    assert est.test_orders == result.test_rows and est.test_start >= result.split_date
    assert est.label_source == result.label_source


def test_the_flagged_orders_are_more_often_returned_than_orders_in_general(trained):
    """If flagging did not beat chance, the estimate would be worthless. In the made-up data
    big orders are returned far more often, so the flagged share must be clearly higher."""
    orders, result = trained
    est = savings_estimate(result, orders, 1.0)
    overall = est.total_returned / est.test_orders
    assert est.flagged_orders > 0 and est.flagged_precision > overall


def test_no_estimate_when_the_model_is_not_trusted():
    orders = make_orders(signal=False)
    assert savings_estimate(train_order_risk(orders), orders, 100.0) is None


@pytest.mark.parametrize("bad", [-1.0, math.nan, math.inf, 2_000_000.0, "100", None, True])
def test_a_shipping_cost_that_cannot_be_real_is_refused(bad):
    with pytest.raises(ValueError):
        check_shipping_cost(bad)


def test_assessing_everything_still_covers_every_test_order(trained):
    orders, result = trained
    assessed = assess_orders(result, orders)
    assert all(o.order_id in assessed for o in orders_tested_on(result, orders))
