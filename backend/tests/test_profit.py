"""Profit Check formulas, worked by hand. All numbers are invented examples."""

import pytest

from app.core.errors import ApiError
from app.services.profit import ProfitInputs, calculate


def inputs(**changes):
    base = dict(cost=1000, price=2500, packing=50, courier_fee=250, return_shipping=150, return_rate=0.2, ad_budget=10000)
    base.update(changes)
    return ProfitInputs(**base)


def test_hand_worked_example():
    r = calculate(inputs())
    # delivered: 2500 - 1000 - 50 - 250 = 1200.   returned loses 50 + 250 + 150 = 450.
    assert r.profit_delivered == 1200 and r.loss_returned == 450
    # per order placed: 0.8 * 1200 - 0.2 * 450 = 960 - 90 = 870
    assert r.profit_per_order_placed == 870
    assert r.margin == pytest.approx(870 / 2500, abs=1e-4)
    assert r.break_even_cost_per_purchase == 870
    assert r.break_even_roas == pytest.approx(2500 / 870, abs=0.01)            # 2.87
    assert r.orders_to_recover_budget == 12                                    # ceil(10000 / 870) = 12 (11.49)
    assert r.warnings == []


def test_no_returns_means_the_delivered_profit():
    r = calculate(inputs(return_rate=0))
    assert r.profit_per_order_placed == r.profit_delivered == 1200


def test_every_order_returned_loses_the_return_costs():
    r = calculate(inputs(return_rate=1))
    assert r.profit_per_order_placed == -450 and "loss_per_order" in r.warnings
    assert r.break_even_roas is None and r.break_even_cost_per_purchase is None and r.orders_to_recover_budget is None


def test_a_negative_profit_per_order_warns_and_has_no_break_even():
    r = calculate(inputs(price=1200))                                          # delivered: 1200-1000-50-250 = -100
    assert r.profit_delivered == -100
    assert {"loss_per_order", "loss_when_delivered"} <= set(r.warnings)
    assert r.break_even_roas is None


def test_a_thin_margin_under_10_percent_warns():
    r = calculate(inputs(price=1500, return_rate=0))                           # 1500-1000-50-250 = 200 -> 13.3%: not thin
    assert "thin_margin" not in r.warnings
    r = calculate(inputs(price=1380, return_rate=0))                           # 80 -> 5.8%: thin
    assert "thin_margin" in r.warnings and "loss_per_order" not in r.warnings


def test_exactly_10_percent_is_not_thin():
    r = calculate(ProfitInputs(cost=900, price=1000, packing=0, courier_fee=0, return_shipping=0, return_rate=0, ad_budget=0))
    assert r.margin == 0.1 and "thin_margin" not in r.warnings


def test_no_ad_budget_is_noted_and_needs_no_orders():
    r = calculate(inputs(ad_budget=0))
    assert r.orders_to_recover_budget is None and "no_budget" in r.warnings


def test_orders_needed_rounds_up():
    r = calculate(inputs(ad_budget=870))
    assert r.orders_to_recover_budget == 1
    assert calculate(inputs(ad_budget=871)).orders_to_recover_budget == 2


@pytest.mark.parametrize("changes", [dict(price=0), dict(cost=-1), dict(return_rate=1.5), dict(return_rate=-0.1),
                                      dict(ad_budget=float("nan")), dict(packing=float("inf")), dict(price=1e12)])
def test_numbers_that_cannot_be_real_are_refused(changes):
    with pytest.raises(ApiError) as caught:
        calculate(inputs(**changes))
    assert caught.value.status_code == 422
