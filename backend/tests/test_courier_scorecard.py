"""The Courier Scorecard: rates, the minimum-count rule and the real/demo split.

Every shipment here is invented for the test (courier "TESTCOURIER", cities "Testville"...)."""

from datetime import date, timedelta
from itertools import count

import pytest

from app.models import Shipment
from app.models.shipment import SOURCE_DEMO
from app.services import data_rules
from app.services.courier_scorecard import compute_scorecard

_ids = count(1)
DAY0 = date(2026, 1, 1)


def add(db, courier, city, status, n=1, *, source="import", refused=False, days=3, booked=DAY0):
    for _ in range(n):
        closed = booked + timedelta(days=days) if status in ("delivered", "returned") else None
        db.add(Shipment(external_id=f"T-{next(_ids)}", courier=courier, city=city, booked_date=booked,
                        closed_date=closed, status=status, refused=refused, source=source))
    db.flush()


def find(card, courier, city):
    return next(r for r in card.rows if r.courier == courier and r.city == city)


def test_rates_use_closed_parcels_only(db_session):
    add(db_session, "TESTCOURIER", "Testville", "delivered", 16)
    add(db_session, "TESTCOURIER", "Testville", "returned", 4, refused=True)
    add(db_session, "TESTCOURIER", "Testville", "in_transit", 5)      # no result yet: not in the rate
    add(db_session, "TESTCOURIER", "Testville", "lost", 2)
    row = find(compute_scorecard(db_session), "TESTCOURIER", "Testville")
    assert (row.shipments, row.closed, row.in_transit, row.lost, row.refused) == (27, 20, 5, 2, 4)
    assert row.enough and row.delivery_rate == 0.8 and row.return_rate == 0.2 and row.average_days == 3.0


def test_nineteen_closed_parcels_is_not_enough_and_twenty_is(db_session):
    assert data_rules.MIN_GROUP_COUNT == 20
    add(db_session, "TESTCOURIER", "Testville", "delivered", 19)
    add(db_session, "TESTCOURIER", "Otherton", "delivered", 20)
    card = compute_scorecard(db_session)
    small, big = find(card, "TESTCOURIER", "Testville"), find(card, "TESTCOURIER", "Otherton")
    assert not small.enough and small.needed == 1
    assert small.delivery_rate is None and small.return_rate is None and small.average_days is None
    assert small.shipments == 19                                       # the count is still shown
    assert big.enough and big.needed == 0 and big.delivery_rate == 1.0


def test_unfinished_parcels_do_not_help_a_group_reach_the_minimum(db_session):
    add(db_session, "TESTCOURIER", "Testville", "delivered", 10)
    add(db_session, "TESTCOURIER", "Testville", "in_transit", 30)
    row = find(compute_scorecard(db_session), "TESTCOURIER", "Testville")
    assert row.shipments == 40 and not row.enough and row.needed == 10


def test_a_courier_with_no_city_is_its_own_row(db_session):
    add(db_session, "TESTCOURIER", None, "delivered", 3)
    card = compute_scorecard(db_session)
    assert find(card, "TESTCOURIER", None).shipments == 3 and card.all_cities == []


def test_courier_summary_adds_up_the_cities(db_session):
    add(db_session, "TESTCOURIER", "Testville", "delivered", 12)
    add(db_session, "TESTCOURIER", "Otherton", "returned", 8)
    card = compute_scorecard(db_session)
    total = next(c for c in card.couriers if c.courier == "TESTCOURIER")
    assert total.closed == 20 and total.enough and total.return_rate == 0.4


def test_auto_shows_real_data_and_hides_demo_when_real_exists(db_session):
    add(db_session, "TESTCOURIER", "Testville", "delivered", 5)
    add(db_session, "DEMOCOURIER", "Testville", "delivered", 50, source=SOURCE_DEMO)
    card = compute_scorecard(db_session)
    assert card.source_used == "real" and (card.real_shipments, card.demo_shipments) == (5, 50)
    assert {r.courier for r in card.rows} == {"TESTCOURIER"}
    assert {r.courier for r in compute_scorecard(db_session, source="demo").rows} == {"DEMOCOURIER"}
    assert {r.courier for r in compute_scorecard(db_session, source="all").rows} == {"TESTCOURIER", "DEMOCOURIER"}


def test_auto_falls_back_to_demo_when_there_is_nothing_real(db_session):
    add(db_session, "DEMOCOURIER", "Testville", "delivered", 5, source=SOURCE_DEMO)
    assert compute_scorecard(db_session).source_used == "demo"


def test_period_counts_back_from_the_latest_booked_date(db_session):
    add(db_session, "TESTCOURIER", "Testville", "delivered", 4, booked=DAY0)
    add(db_session, "TESTCOURIER", "Testville", "delivered", 6, booked=DAY0 + timedelta(days=100))
    card = compute_scorecard(db_session, days=30)
    assert card.period_end == DAY0 + timedelta(days=100) and card.shipments == 6


def test_city_and_courier_filters(db_session):
    add(db_session, "TESTCOURIER", "Testville", "delivered", 2)
    add(db_session, "TESTCOURIER", "Otherton", "delivered", 3)
    add(db_session, "OTHERCOURIER", "Testville", "delivered", 4)
    card = compute_scorecard(db_session, city="Testville")
    assert card.shipments == 6 and card.all_cities == ["Otherton", "Testville"]   # the filter lists stay full
    assert compute_scorecard(db_session, courier="OTHERCOURIER").shipments == 4


def test_empty_database_gives_an_empty_scorecard(db_session):
    card = compute_scorecard(db_session)
    assert card.rows == [] and card.couriers == [] and card.shipments == 0 and card.period_end is None


def test_endpoint_shape_and_validation(db_client, db_session):
    add(db_session, "TESTCOURIER", "Testville", "delivered", 20)
    body = db_client.get("/api/v1/couriers/scorecard").json()
    row = body["rows"][0]
    assert body["minGroupCount"] == 20 and body["sourceUsed"] == "real"
    assert row["courier"] == "TESTCOURIER" and row["deliveryRate"] == 1.0 and row["enough"] is True
    assert db_client.get("/api/v1/couriers/scorecard?source=bogus").status_code == 422
    assert db_client.get("/api/v1/couriers/scorecard?days=0").status_code == 422


def test_suggestion_picks_the_lowest_return_rate_among_couriers_with_enough_history(db_session):
    from app.services.courier_scorecard import suggest_courier

    add(db_session, "AAA", "Lahore", "delivered", 18)
    add(db_session, "AAA", "Lahore", "returned", 7)            # 28% returned, 25 finished
    add(db_session, "BBB", "Lahore", "delivered", 22)
    add(db_session, "BBB", "Lahore", "returned", 3)            # 12% returned, 25 finished
    add(db_session, "CCC", "Lahore", "delivered", 10)          # 0% returned but only 10 finished: ignored
    found = suggest_courier(db_session, "lahore ")
    assert found.available and found.city == "Lahore"
    assert found.best.courier == "BBB" and [o.courier for o in found.others] == ["AAA"]


def test_no_suggestion_when_no_courier_has_enough_history(db_session):
    from app.services.courier_scorecard import suggest_courier

    add(db_session, "AAA", "Lahore", "delivered", 19)
    found = suggest_courier(db_session, "Lahore")
    assert not found.available and found.best is None
    assert suggest_courier(db_session, "  ") is None


def test_suggest_endpoint(db_client, db_session):
    add(db_session, "AAA", "Lahore", "delivered", 20)
    body = db_client.get("/api/v1/couriers/suggest?city=Lahore").json()
    assert body["available"] is True and body["best"]["courier"] == "AAA"
    assert db_client.get("/api/v1/couriers/suggest?city=Nowhereville").json()["available"] is False
