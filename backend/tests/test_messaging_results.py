"""Auto Messenger part 6: results, the messaged-vs-holdout comparison, and the cost estimate. Made-up data (TEST)."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from math import sqrt

import pytest

from app.core.config import get_settings, Settings
from app.main import app
from app.models import Campaign, ConsentEvent, Customer, Journey, JourneyEnrollment, Message, MessageTemplate, Order
from app.services.messaging import consent, journeys, results
from app.services.messaging.results import MIN_MESSAGING_GROUP, compare, two_proportion_interval
from app.services.messaging.settings_store import get_row

_n = [0]
TODAY = datetime.now(timezone.utc)


# --- the statistics (pure) ----------------------------------------------------------------------------------------------------------


def test_the_interval_matches_a_hand_calculation():
    # 18 of 60 ordered after messages, 8 of 50 in the holdout: 30% vs 16%.
    diff, low, high = two_proportion_interval(18, 60, 8, 50)
    spread = 1.96 * sqrt(0.3 * 0.7 / 60 + 0.16 * 0.84 / 50)
    assert diff == pytest.approx(0.14) and low == pytest.approx(0.14 - spread) and high == pytest.approx(0.14 + spread)
    assert low < 0 < 0.14 < high < 0.3                                                          # +14 points, but the interval (-1.4 to +29.4) includes 0: this size of group could not rule out chance


def test_a_group_below_the_minimum_gives_no_result_only_how_many_more_are_needed():
    assert MIN_MESSAGING_GROUP == 30
    c = compare(10, 29, 4, 100)
    assert (c.enough, c.messaged, c.holdout, c.needed, c.difference, c.low, c.high, c.messaged_rate) == (False, 29, 100, 1, None, None, None, None)
    assert compare(10, 100, 4, 5).needed == 25 and compare(0, 0, 0, 0).needed == 30
    assert compare(10, 30, 4, 30).enough is True                                                # exactly 30 in each: enough


def test_a_gap_that_could_be_chance_is_flagged():
    chance = compare(15, 100, 13, 100)                                                         # 15% vs 13%
    assert chance.enough and chance.could_be_chance is True and chance.low < 0 < chance.high
    real = compare(60, 100, 20, 100)
    assert real.could_be_chance is False and real.low > 0 and real.difference == pytest.approx(0.4)
    reverse = compare(10, 100, 40, 100)
    assert reverse.could_be_chance is False and reverse.high < 0                               # messaging made it worse, and that is shown too


def test_revenue_per_customer_is_an_average_over_each_group():
    c = compare(20, 40, 10, 40, messaged_revenue=80000.0, holdout_revenue=20000.0)
    assert (c.messaged_revenue, c.holdout_revenue) == (2000.0, 500.0)


# --- helpers --------------------------------------------------------------------------------------------------------------------------


def customer(db, name="Test Ali"):
    _n[0] += 1
    c = Customer(external_id=f"TEST-R{_n[0]}", first_name=name, phone=f"+92300{_n[0]:07d}", phone_normalised=f"+92300{_n[0]:07d}", email=f"r{_n[0]}.test@testcustomer.test", country="Pakistan")
    db.add(c)
    db.flush()
    return c


def template(db, category="utility", channel="whatsapp"):
    _n[0] += 1
    t = MessageTemplate(name=f"test_res_{_n[0]}", channel=channel, category=category, language="en", body="Hi {{first_name}}", approved_by_seller=True)
    db.add(t)
    db.flush()
    return t


def message(db, c, t, *, days_ago=10, status="sent", dry_run=False, delivered=True, read=False, replied=False, journey_id=None, campaign_id=None):
    _n[0] += 1
    sent_at = TODAY - timedelta(days=days_ago)
    m = Message(
        customer_id=c.id, channel=t.channel, template_id=t.id, category=t.category, rendered_text="x", status=status, idempotency_key=f"test-res-{_n[0]}", dry_run=dry_run,
        queued_at=sent_at, sent_at=sent_at if status != "skipped" else None, delivered_at=sent_at if delivered and status != "skipped" else None,
        read_at=sent_at if read else None, replied_at=sent_at if replied else None, journey_id=journey_id, campaign_id=campaign_id,
    )
    db.add(m)
    db.flush()
    return m


def order(db, c, day, value=1000):
    _n[0] += 1
    o = Order(external_id=f"TEST-RO-{_n[0]}", customer_id=c.id, order_date=day, order_value=Decimal(value), source="manual")
    db.add(o)
    db.flush()
    return o


# --- per template, campaign and journey ------------------------------------------------------------------------------------------


def test_counts_per_template_cover_the_whole_delivery_chain(db_session):
    t = template(db_session)
    a, b, c, d = (customer(db_session) for _ in range(4))
    message(db_session, a, t, read=True)
    message(db_session, b, t, replied=True)
    message(db_session, c, t, status="failed", delivered=False)
    message(db_session, d, t, status="skipped")
    group = results.build(db_session)["templates"][0]
    assert (group.sent, group.delivered, group.read, group.replied, group.failed, group.skipped) == (3, 3 - 1, 1, 1, 1, 1)


def test_each_group_is_counted_separately_and_unlinked_messages_are_left_out_of_campaigns_and_journeys(db_session):
    t = template(db_session)
    campaign = Campaign(name="Test campaign", status="sending", audience={})
    journey = Journey(key="test_j", name="Test journey", trigger_segment="Champions", steps=[{"day": 0, "event": "x"}])
    db_session.add_all([campaign, journey])
    db_session.flush()
    a, b = customer(db_session), customer(db_session)
    message(db_session, a, t, campaign_id=campaign.id)
    message(db_session, b, t, campaign_id=campaign.id)
    message(db_session, a, t, journey_id=journey.id)
    message(db_session, b, t)
    data = results.build(db_session)
    assert [(g.name, g.sent) for g in data["campaigns"]] == [("Test campaign", 2)]
    assert [(g.name, g.sent) for g in data["journeys"].values()] == [("Test journey", 1)]
    assert data["templates"][0].sent == 4 and data["totals"]["sent"] == 4


def test_orders_within_seven_days_are_counted_once_per_group_and_not_before_or_after(db_session):
    t = template(db_session)
    c = customer(db_session)
    message(db_session, c, t, days_ago=10)
    message(db_session, c, t, days_ago=9)                                                       # a second message to the same customer
    sent_day = (TODAY - timedelta(days=10)).date()
    order(db_session, c, sent_day - timedelta(days=1), 500)                                    # the day BEFORE the message: not counted
    inside = order(db_session, c, sent_day + timedelta(days=2), 1200)
    edge = order(db_session, c, sent_day + timedelta(days=7), 800)
    order(db_session, c, sent_day + timedelta(days=30), 9999)                                  # long after: not counted
    group = results.build(db_session)["templates"][0]
    assert group.orders == 2 and group.revenue == 2000.0 and inside.id and edge.id               # each order once, though two messages reach it


def test_a_dry_run_message_is_left_out_unless_asked_for(db_session):
    t = template(db_session)
    c = customer(db_session)
    message(db_session, c, t, dry_run=True)
    message(db_session, c, t, dry_run=False)
    assert results.build(db_session)["templates"][0].sent == 1
    assert results.build(db_session, include_dry_run=True)["templates"][0].sent == 2


def test_the_period_limits_which_messages_count(db_session):
    t = template(db_session)
    c = customer(db_session)
    message(db_session, c, t, days_ago=10)
    message(db_session, c, t, days_ago=100)
    assert results.build(db_session, days=90)["templates"][0].sent == 1 and results.build(db_session, days=365)["templates"][0].sent == 2


def test_an_opt_out_is_blamed_on_the_last_message_before_it_within_seven_days(db_session):
    first, second = template(db_session, "marketing"), template(db_session, "marketing")
    c, other = customer(db_session), customer(db_session)
    message(db_session, c, first, days_ago=6)
    message(db_session, c, second, days_ago=3)                                                  # the last one before the opt-out
    message(db_session, other, first, days_ago=20)                                              # too long before the opt-out below
    for who, days_ago in ((c, 2), (other, 1)):
        consent.set_consent(db_session, who.id, "whatsapp", True, "manual")
        consent.set_consent(db_session, who.id, "whatsapp", False, "whatsapp_stop")
        for e in db_session.query(ConsentEvent).filter_by(customer_id=who.id, action="opt_out"):
            e.at = TODAY - timedelta(days=days_ago)
    db_session.flush()
    by_name = {g.name: g for g in results.build(db_session)["templates"]}
    assert by_name[second.name].opt_outs == 1 and by_name[first.name].opt_outs == 0
    assert results.build(db_session)["totals"]["opt_outs"] == 1


def test_an_opt_out_on_another_channel_is_not_blamed_on_a_whatsapp_message(db_session):
    t = template(db_session, "marketing")
    c = customer(db_session)
    message(db_session, c, t, days_ago=3)
    consent.set_consent(db_session, c.id, "email", True, "manual")
    consent.set_consent(db_session, c.id, "email", False, "email_unsubscribe")
    for e in db_session.query(ConsentEvent).filter_by(action="opt_out"):
        e.at = TODAY - timedelta(days=2)
    db_session.flush()
    assert results.build(db_session)["templates"][0].opt_outs == 0


# --- the cost estimate ------------------------------------------------------------------------------------------------------------


def test_the_cost_is_messages_times_the_price_the_seller_typed_and_never_a_built_in_price(db_session):
    utility, marketing, mail = template(db_session), template(db_session, "marketing"), template(db_session, channel="email")
    c = customer(db_session)
    for _ in range(3):
        message(db_session, c, utility)
    for _ in range(2):
        message(db_session, c, marketing)
    message(db_session, c, mail)                                                                # email: not a WhatsApp cost
    cost = results.build(db_session)["cost"]
    assert cost == {"utility_messages": 3, "marketing_messages": 2, "utility_rate": None, "marketing_rate": None}   # no price entered, so none is used
    row = get_row(db_session)
    row.cost_utility, row.cost_marketing = Decimal("1.5"), Decimal("4")
    db_session.flush()
    cost = results.build(db_session)["cost"]
    assert cost["utility_rate"] == 1.5 and cost["marketing_rate"] == 4.0 and cost["utility_messages"] == 3


# --- messaged vs holdout ----------------------------------------------------------------------------------------------------------------


def make_journey(db):
    j = Journey(key="test_cmp", name="Test comparison", trigger_segment="At-Risk Customers", steps=[{"day": 0, "event": "journey_at_risk_1"}], enabled=True)
    db.add(j)
    db.flush()
    return j


def enrol(db, j, *, holdout, ordered, days_ago=20, value=1000):
    c = customer(db)
    anchor = TODAY - timedelta(days=days_ago)
    db.add(JourneyEnrollment(journey_id=j.id, customer_id=c.id, enrolled_at=anchor, anchor_at=anchor, holdout=holdout, state="holdout" if holdout else "completed"))
    if ordered:
        order(db, c, anchor.date() + timedelta(days=3), value)
    db.flush()
    return c


def test_the_comparison_uses_the_seven_days_from_the_first_message_for_both_groups(db_session):
    j = make_journey(db_session)
    t = template(db_session, "marketing")
    for i in range(40):                                                                         # 40 messaged customers, 20 ordered
        c = enrol(db_session, j, holdout=False, ordered=i < 20, value=1000)
        message(db_session, c, t, days_ago=20, journey_id=j.id)
    for i in range(35):                                                                         # 35 holdout customers, 7 ordered
        enrol(db_session, j, holdout=True, ordered=i < 7, value=500)
    comparison = results.journey_comparison(db_session, j, datetime.now(timezone.utc), include_dry_run=False)
    assert comparison.enough and (comparison.messaged, comparison.holdout) == (40, 35)
    assert comparison.messaged_rate == pytest.approx(0.5) and comparison.holdout_rate == pytest.approx(0.2) and comparison.difference == pytest.approx(0.3)
    assert comparison.could_be_chance is False and comparison.messaged_revenue == pytest.approx(500.0) and comparison.holdout_revenue == pytest.approx(100.0)


def test_with_fewer_than_thirty_in_either_group_the_page_says_not_enough_data_yet(db_session):
    j = make_journey(db_session)
    t = template(db_session, "marketing")
    for i in range(50):
        message(db_session, enrol(db_session, j, holdout=False, ordered=True), t, days_ago=20, journey_id=j.id)
    for i in range(29):
        enrol(db_session, j, holdout=True, ordered=False)
    comparison = results.journey_comparison(db_session, j, datetime.now(timezone.utc), include_dry_run=False)
    assert (comparison.enough, comparison.needed, comparison.difference) == (False, 1, None) and (comparison.messaged, comparison.holdout) == (50, 29)


def test_customers_whose_seven_days_are_not_over_yet_are_left_out(db_session):
    j = make_journey(db_session)
    t = template(db_session, "marketing")
    for i in range(35):
        message(db_session, enrol(db_session, j, holdout=False, ordered=True, days_ago=20), t, days_ago=20, journey_id=j.id)
        enrol(db_session, j, holdout=True, ordered=False, days_ago=20)
    for i in range(20):                                                                         # only 2 days old: no result for them yet
        enrol(db_session, j, holdout=False, ordered=False, days_ago=2)
        enrol(db_session, j, holdout=True, ordered=False, days_ago=2)
    comparison = results.journey_comparison(db_session, j, datetime.now(timezone.utc), include_dry_run=False)
    assert (comparison.messaged, comparison.holdout) == (35, 35)


def test_everyone_meant_to_be_messaged_counts_even_if_a_message_was_skipped(db_session):
    """Intention to treat: dropping the customers whose message was skipped would flatter the messages."""
    j = make_journey(db_session)
    t = template(db_session, "marketing")
    message(db_session, enrol(db_session, j, holdout=False, ordered=False), t, days_ago=20, journey_id=j.id)       # one real message makes the comparison valid
    for i in range(39):
        enrol(db_session, j, holdout=False, ordered=False)                                       # enrolled, but never actually messaged
    for i in range(30):
        enrol(db_session, j, holdout=True, ordered=False)
    comparison = results.journey_comparison(db_session, j, datetime.now(timezone.utc), include_dry_run=False)
    assert comparison.messaged == 40


def test_a_journey_that_only_ran_in_dry_run_has_no_comparison_until_asked(db_session):
    j = make_journey(db_session)
    t = template(db_session, "marketing")
    message(db_session, enrol(db_session, j, holdout=False, ordered=False), t, days_ago=20, dry_run=True, journey_id=j.id)
    for i in range(40):
        enrol(db_session, j, holdout=True, ordered=False)
    assert results.journey_comparison(db_session, j, datetime.now(timezone.utc), include_dry_run=False).reason == "no_real_messages"
    assert results.journey_comparison(db_session, j, datetime.now(timezone.utc), include_dry_run=True).reason is None


def test_a_brand_new_journey_has_nothing_to_compare_yet(db_session):
    j = make_journey(db_session)
    t = template(db_session, "marketing")
    message(db_session, customer(db_session), t, journey_id=j.id)
    comparison = results.journey_comparison(db_session, j, datetime.now(timezone.utc), include_dry_run=False)
    assert comparison.enough is False and comparison.reason == "too_new" and comparison.needed == 30


# --- HTTP ---------------------------------------------------------------------------------------------------------------------------------


def test_the_results_endpoint(db_client, db_session):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, messaging_dry_run=True)
    t, m = template(db_session), template(db_session, "marketing")
    c = customer(db_session)
    message(db_session, c, t)
    message(db_session, c, m, read=True)
    order(db_session, c, (TODAY - timedelta(days=9)).date(), 1500)
    j = make_journey(db_session)
    empty = db_client.get("/api/v1/messaging/results?includeDryRun=true").json()
    assert empty["minGroupCount"] == 30 and empty["totals"]["sent"] == 2 and empty["totals"]["orders"] >= 1
    assert empty["cost"] == {"utilityMessages": 1, "marketingMessages": 1, "utilityRate": None, "marketingRate": None, "total": None}
    body = db_client.get("/api/v1/messaging/results").json()
    assert body["totals"]["sent"] == 2 and {g["name"] for g in body["templates"]} == {t.name, m.name}
    journey_row = next(x for x in body["journeys"] if x["journeyId"] == j.id)
    assert journey_row["comparison"]["enough"] is False and journey_row["comparison"]["reason"] == "no_real_messages"
    db_client.put("/api/v1/messaging/settings", json={"costUtility": 1.5, "costMarketing": 4})
    priced = db_client.get("/api/v1/messaging/results").json()
    assert priced["cost"]["total"] == 5.5 and sorted(g["whatsappCost"] for g in priced["templates"]) == [1.5, 4.0]
    assert db_client.get("/api/v1/messaging/results?days=0").status_code == 422 and db_client.get("/api/v1/messaging/results?days=400").status_code == 422
