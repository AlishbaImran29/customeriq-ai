"""Order Risk features: the no-leakage rule, and each feature on a tiny hand-made history."""

import math
from datetime import date, datetime

from app.services.order_features import NUMERIC_FEATURES, OrderInput, build_order_features


def order(order_id, day, value=100.0, customer="C1", **kw):
    """An order on `day` (an ISO date). `ordered_at` may be given as a datetime in `kw`."""
    return OrderInput(order_id=order_id, customer_id=customer, order_date=date.fromisoformat(day), value=value, **kw)


def test_first_order_of_a_customer_has_no_history():
    f = build_order_features([order("O1", "2026-01-10", 80.0)])["O1"]
    assert (f.past_orders, f.is_new_customer) == (0, 1)
    # Missing history is missing (None), never 0%: a new customer is not a "perfect" customer.
    assert f.past_cancel_rate is None and f.days_since_previous_order is None
    assert f.value_vs_customer_avg is None


def test_history_features_use_only_earlier_orders():
    orders = [
        order("O1", "2026-01-01", 100.0, outcome="delivered"),
        order("O2", "2026-01-11", 300.0, outcome="returned", outcome_date=date(2026, 1, 20)),
        order("O3", "2026-02-01", 400.0),
    ]
    f = build_order_features(orders)["O3"]
    assert f.past_orders == 2 and f.is_new_customer == 0
    assert f.past_cancel_rate == 0.5                      # 1 returned (known on Jan 20) of 2
    assert f.days_since_previous_order == 21              # Jan 11 -> Feb 1
    assert f.value_vs_customer_avg == 2.0                 # 400 / average(100, 300)


def test_a_return_is_counted_only_once_it_was_known():
    # O1 was returned, but the courier said so on 2026-01-20.
    first = order("O1", "2026-01-01", outcome="returned", outcome_date=date(2026, 1, 20))
    rates = {
        day: build_order_features([first, order("O2", day)])["O2"].past_cancel_rate
        for day in ("2026-01-19", "2026-01-20", "2026-01-21")
    }
    assert rates["2026-01-19"] == 0.0     # not known yet
    assert rates["2026-01-20"] == 0.0     # known the same day: still treated as not known (strict)
    assert rates["2026-01-21"] == 1.0     # known the day before


def test_a_return_without_a_date_is_never_counted():
    f = build_order_features([order("O1", "2026-01-01", outcome="returned"), order("O2", "2026-02-01")])["O2"]
    assert f.past_cancel_rate == 0.0


def test_own_outcome_never_changes_own_features():
    base = [order("O1", "2026-01-01"), order("O2", "2026-01-05", outcome="delivered")]
    flipped = [order("O1", "2026-01-01"), order("O2", "2026-01-05", outcome="returned", outcome_date=date(2026, 1, 9))]
    assert build_order_features(base)["O2"] == build_order_features(flipped)["O2"]


def test_later_orders_never_change_earlier_features():
    """The core leakage test: add the future and no earlier row may change."""
    orders = [
        order("O1", "2026-01-01", 50.0, outcome="returned", outcome_date=date(2026, 1, 3)),
        order("O2", "2026-01-10", 120.0, outcome="delivered"),
        order("O3", "2026-02-01", 90.0, outcome="returned", outcome_date=date(2026, 2, 5)),
        order("O4", "2026-03-01", 500.0),
        order("X1", "2026-01-15", 70.0, customer="C2"),
    ]
    everything = build_order_features(orders)
    ordered = sorted(orders, key=lambda o: (o.order_date, o.order_id))
    for cut in range(1, len(ordered) + 1):
        only_the_past = build_order_features(ordered[:cut])
        for oid, features in only_the_past.items():
            assert features == everything[oid], f"{oid} changed when later orders were added"


def test_an_order_placed_at_the_same_moment_is_not_history():
    t = datetime(2026, 1, 5, 14, 30)
    f = build_order_features([
        order("O1", "2026-01-05", ordered_at=t), order("O2", "2026-01-05", ordered_at=t),
    ])
    assert f["O1"].past_orders == 0 and f["O2"].past_orders == 0


def test_same_day_orders_without_a_time_are_not_history_either():
    f = build_order_features([order("O1", "2026-01-05"), order("O2", "2026-01-05")])
    assert f["O1"].past_orders == 0 and f["O2"].past_orders == 0


def test_time_of_day_is_missing_when_not_given_but_weekday_is_known():
    f = build_order_features([
        order("O1", "2026-01-05"),                                           # a Monday, no time
        order("O2", "2026-01-06", ordered_at=datetime(2026, 1, 6, 23, 15)),  # a Tuesday, 23:15
    ])
    assert f["O1"].hour is None and f["O1"].weekday == 0
    assert f["O2"].hour == 23 and f["O2"].weekday == 1


def test_order_facts_are_passed_through_and_missing_ones_become_nan():
    f = build_order_features([
        order("O1", "2026-01-05", item_count=3, distinct_products=2, country="Pakistan",
              address_length=40, has_house_number=True, phone_valid=False),
        order("O2", "2026-01-06", customer="C2"),
    ])
    row = dict(zip(NUMERIC_FEATURES, f["O1"].numeric_row()))
    assert (row["item_count"], row["distinct_products"], row["has_house_number"], row["phone_valid"]) == (3, 2, 1, 0)
    assert f["O1"].country == "Pakistan"
    empty = dict(zip(NUMERIC_FEATURES, f["O2"].numeric_row()))
    assert math.isnan(empty["item_count"]) and math.isnan(empty["phone_valid"]) and math.isnan(empty["hour"])


def test_customers_do_not_share_history():
    f = build_order_features([
        order("A1", "2026-01-01", customer="A", outcome="returned", outcome_date=date(2026, 1, 2)),
        order("B1", "2026-02-01", customer="B"),
    ])
    assert f["B1"].past_orders == 0 and f["B1"].is_new_customer == 1
