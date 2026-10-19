"""Dashboard channel filter, revenue by channel, and the "X more needed" messages. All data is made up."""

from datetime import date, timedelta

import pytest

from app.services import analytics as a
from app.services import predictions as pr
from tests.conftest import requires_database
from tests.test_imports_api import upload

HEAD = "order_id,order_date,order_value,phone,channel"


@pytest.fixture(autouse=True)
def fresh_cache():
    pr._cache.clear()
    yield
    pr._cache.clear()


def day(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def import_orders(client):
    """Three channels: Instagram 2 orders (1 customer), WhatsApp 2 orders (2 customers), Website 1 order."""
    lines = [
        HEAD,
        f"I1,{day(10)},1000,0300 1111111,Instagram",
        f"I2,{day(5)},500,0300 1111111,insta",
        f"W1,{day(8)},200,0321 2222222,WhatsApp",
        f"W2,{day(3)},300,0345 3333333,wa",
        f"S1,{day(2)},4000,0333 4444444,Shopify (web)",
    ]
    assert upload(client, "\n".join(lines)).status_code == 201


def overview(client, **params):
    response = client.get("/api/v1/dashboard/overview", params=params)
    assert response.status_code == 200, response.text
    return response.json()


@requires_database
def test_revenue_by_channel_lists_all_five_channels_with_their_totals(db_client):
    import_orders(db_client)
    body = overview(db_client)
    rows = {r["channel"]: r for r in body["revenueByChannel"]}
    assert list(rows) == ["website", "instagram", "whatsapp", "facebook", "other"] or set(rows) == {"instagram", "whatsapp", "facebook", "website", "other"}
    assert body["revenueByChannel"][0]["channel"] == "website"                                # biggest first
    assert (rows["instagram"]["revenue"], rows["instagram"]["orders"], rows["instagram"]["customers"]) == (1500.0, 2, 1)
    assert (rows["whatsapp"]["revenue"], rows["whatsapp"]["orders"], rows["whatsapp"]["customers"]) == (500.0, 2, 2)
    assert (rows["website"]["revenue"], rows["facebook"]["revenue"], rows["other"]["orders"]) == (4000.0, 0.0, 0)
    assert sum(r["revenue"] for r in rows.values()) == 6000.0
    assert body["channelPeriodEnd"] == day(2) and body["channel"] is None


@requires_database
def test_the_channel_filter_changes_the_figures_but_not_the_chart(db_client):
    import_orders(db_client)
    everyone = overview(db_client)
    whatsapp = overview(db_client, channel="whatsapp")
    assert everyone["kpis"]["totalCustomers"] == 4 and whatsapp["kpis"]["totalCustomers"] == 2        # 2 WhatsApp customers
    assert whatsapp["meta"]["customerCount"] == 2 and whatsapp["channel"] == "whatsapp"
    assert whatsapp["revenueByChannel"] == everyone["revenueByChannel"]                            # the chart always compares all
    insta = overview(db_client, channel="instagram")
    assert insta["kpis"]["totalCustomers"] == 1 and insta["meta"]["asOf"] == day(5)


@requires_database
def test_all_and_empty_mean_no_filter_and_a_bad_channel_is_refused(db_client):
    import_orders(db_client)
    assert overview(db_client, channel="all")["channel"] is None and overview(db_client, channel="")["channel"] is None
    assert overview(db_client, channel="all")["kpis"] == overview(db_client)["kpis"]
    bad = db_client.get("/api/v1/dashboard/overview", params={"channel": "tiktok"})
    assert bad.status_code == 422 and "Choose a channel" in bad.json()["error"]["message"]


@requires_database
def test_a_channel_with_no_orders_gives_an_empty_page_not_an_error(db_client):
    import_orders(db_client)
    body = overview(db_client, channel="facebook")
    assert body["meta"]["asOf"] is None and body["meta"]["customerCount"] == 0 and body["channel"] == "facebook"
    assert any(r["channel"] == "website" and r["revenue"] == 4000.0 for r in body["revenueByChannel"])   # the chart still shows the rest


@requires_database
def test_the_chart_period_follows_the_chosen_dates(db_client):
    import_orders(db_client)
    body = overview(db_client, start=day(9), end=day(4))
    rows = {r["channel"]: r for r in body["revenueByChannel"]}
    assert (rows["instagram"]["revenue"], rows["whatsapp"]["revenue"], rows["website"]["revenue"]) == (500.0, 200.0, 0.0)
    assert (body["channelPeriodStart"], body["channelPeriodEnd"]) == (day(9), day(4))


@requires_database
def test_no_data_at_all_gives_an_empty_chart(db_client):
    body = overview(db_client)
    assert body["revenueByChannel"] == [] and body["channelPeriodEnd"] is None and body["segmentsNeeded"] == a.MIN_CUSTOMERS_FOR_SEGMENTS


@requires_database
def test_segments_needed_counts_the_customers_still_missing(db_client):
    import_orders(db_client)
    assert overview(db_client)["segmentsNeeded"] == a.MIN_CUSTOMERS_FOR_SEGMENTS - 4
    assert overview(db_client, channel="instagram")["segmentsNeeded"] == a.MIN_CUSTOMERS_FOR_SEGMENTS - 1


@requires_database
def test_unavailable_predictions_say_how_much_more_data_is_needed(db_client):
    import_orders(db_client)
    reasons = {u["field"]: u["reason"] for u in overview(db_client)["meta"]["unavailable"]}
    assert reasons["churnRisk"].startswith("Not enough data yet: ")
    assert "more days of order history needed" in reasons["churnRisk"]


def test_the_shortage_messages_count_in_the_unit_of_the_rule():
    assert pr._more_days(270, 20) == "Not enough data yet: 250 more days of order history needed (you have 20; it needs at least 270)."
    text = pr._more_customers(200, 37, 180)
    assert text.startswith("Not enough data yet: 163 more customers with order history needed") and "at least 200" in text


def test_models_for_different_channels_are_cached_separately():
    from tests.test_predictions import synthetic_facts

    facts = synthetic_facts(300)
    whole = pr.get_predictions(a.build_snapshot(facts))
    part = pr.get_predictions(a.build_snapshot(facts[: len(facts) // 2]))
    assert part is not whole
    assert pr.get_predictions(a.build_snapshot(facts)) is whole                     # still cached after the other dataset
    assert pr.get_predictions(a.build_snapshot(facts[: len(facts) // 2])) is part
