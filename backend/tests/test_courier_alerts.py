"""The "Unusual returns" alert. All shipments are invented for the tests."""

from types import SimpleNamespace

from app.services.courier_alerts import one_sided_p, unusual_returns
from app.services.courier_scorecard import compute_scorecard
from tests.test_courier_scorecard import add


def g(courier, city, returned, closed):
    return SimpleNamespace(courier=courier, city=city, returned=returned, closed=closed)


def test_p_value_matches_a_hand_worked_example():
    # 20/64 vs 17/120: pooled 37/184 = 0.2011, spread = sqrt(.2011*.7989*(1/64+1/120)) = 0.0620, gap .1708, z = 2.75, one-sided p = 0.003.
    p = one_sided_p(20, 64, 17, 120)
    assert 0.0025 < p < 0.0035


def test_a_clearly_worse_courier_is_flagged_with_counts():
    alerts = unusual_returns([g("A", "Testville", 20, 64), g("B", "Testville", 10, 120)])
    assert len(alerts) == 1
    a = alerts[0]
    assert (a.courier, a.returned, a.closed, a.others_returned, a.others_closed) == ("A", 20, 64, 10, 120)
    assert abs(a.rate - 20 / 64) < 1e-9


def test_a_small_gap_is_not_flagged():
    assert unusual_returns([g("A", "Testville", 16, 100), g("B", "Testville", 14, 100)]) == []


def test_no_alert_when_either_group_is_below_the_minimum():
    assert unusual_returns([g("A", "Testville", 15, 19), g("B", "Testville", 5, 200)]) == []   # A has 19
    assert unusual_returns([g("A", "Testville", 30, 100), g("B", "Testville", 1, 19)]) == []   # others have 19


def test_a_better_than_average_courier_never_alerts():
    assert unusual_returns([g("A", "Testville", 1, 100), g("B", "Testville", 40, 100)])[0].courier == "B"


def test_groups_without_a_city_or_in_other_cities_are_not_mixed():
    assert unusual_returns([g("A", None, 50, 60), g("B", None, 1, 100)]) == []
    assert unusual_returns([g("A", "Testville", 50, 60), g("B", "Otherton", 1, 100)]) == []


def test_scorecard_carries_the_alert_and_keeps_it_when_filtering_to_the_courier(db_session):
    add(db_session, "BADCOURIER", "Testville", "delivered", 40)
    add(db_session, "BADCOURIER", "Testville", "returned", 24)
    add(db_session, "GOODCOURIER", "Testville", "delivered", 110)
    add(db_session, "GOODCOURIER", "Testville", "returned", 10)
    for kwargs in ({}, {"courier": "BADCOURIER"}, {"city": "Testville"}):
        alerts = compute_scorecard(db_session, **kwargs).alerts
        assert [(a.courier, a.city) for a in alerts] == [("BADCOURIER", "Testville")]
    assert compute_scorecard(db_session, courier="GOODCOURIER").alerts == []
