"""Real profit per order and the other money numbers: the formulas, the honesty rules, the HTTP page. Made-up data (TEST)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import AdSpend, Customer, Order, Shipment
from app.models.inventory import StockItem
from app.services import profit_analytics as pa
from app.services.profit_analytics import OrderFacts, order_pnl

D = Decimal
TODAY = date(2026, 3, 10)
_n = [0]


def facts(fate="delivered", value=2500, cost=D(1000), fee=D(200), channel="instagram", items=None):
    return OrderFacts(id=1, number="TEST-1", day=TODAY, channel=channel, city="Lahore", courier="TCS", customer_id=1, customer_name="Test", value=D(value), payment_type="cod", fate=fate,
                      items=items or [("Test shoes", 1)], product_cost=cost, courier_fee=fee)


# --- the formulas (pure) ------------------------------------------------------------------------------------------------------


def test_a_delivered_order_earns_revenue_and_pays_every_cost():
    p = order_pnl(facts(), D(50), D(150), D(100))
    assert (p.revenue, p.profit, p.counted, p.missing) == (D(2500), D(2500 - 1000 - 50 - 200 - 100), True, [])


def test_a_returned_order_earns_nothing_loses_fees_and_keeps_the_product():
    p = order_pnl(facts("returned"), D(50), D(150), D(100))
    assert p.revenue == 0 and p.product_cost == 0                         # the goods come back to the shelf
    assert p.profit == -(50 + 200 + 150 + 100)                            # packing, fee out, return shipping, ad
    assert p.counted and p.missing == []


def test_a_lost_parcel_loses_the_product_too():
    p = order_pnl(facts("lost"), D(50), D(150), D(0))
    assert p.profit == -(1000 + 50 + 200)                                  # no return shipping for a parcel that never came back


def test_a_pending_order_is_not_counted_at_all():
    p = order_pnl(facts("pending"), D(50), D(150), D(100))
    assert (p.counted, p.profit) == (False, 0)


def test_an_unknown_cost_is_never_a_silent_zero():
    p = order_pnl(facts(cost=None), D(50), D(150), D(0))
    assert "product_cost" in p.missing and p.counted is False
    assert order_pnl(facts("returned", cost=None), D(50), D(150), D(0)).counted is True      # a return does not need the product cost
    p = order_pnl(facts(fee=None), None, None, D(0))
    assert p.missing == ["packing", "courier_fee"] and p.counted is True
    assert "return_shipping" in order_pnl(facts("returned"), D(1), None, D(0)).missing


def test_groups_hide_rates_for_small_groups_but_always_show_sums():
    rows = [("Lahore", order_pnl(facts(), D(0), D(0), D(0)), D(1)) for _ in range(3)]
    g = pa._group(rows)[0]
    assert (g.orders, g.profit, g.enough, g.margin, g.profit_per_order, g.return_rate) == (3, D(3900), False, None, None, None)
    big = [("Lahore", order_pnl(facts("returned" if i < 5 else "delivered"), D(0), D(0), D(0)), D(1)) for i in range(25)]
    g = pa._group(big)[0]
    assert g.enough and g.return_rate == pytest.approx(0.2) and g.profit_per_order == pytest.approx(float(g.profit / 25))


def test_a_product_group_shares_an_order_by_units():
    p = order_pnl(facts(items=[("A", 1), ("B", 3)]), D(0), D(0), D(0))
    shares = {name: D(q) / D(4) for name, q in p.facts.items}
    assert shares == {"A": D("0.25"), "B": D("0.75")}


# --- from the database -------------------------------------------------------------------------------------------------------


def customer(db):
    _n[0] += 1
    c = Customer(external_id=f"TEST-PR{_n[0]}", first_name="Test", phone=f"+9230010{_n[0]:05d}", phone_normalised=f"+9230010{_n[0]:05d}")
    db.add(c)
    db.flush()
    return c


def order(db, c, *, value=2500, products="Test shoes", channel="instagram", payment="cod", day=TODAY, status=None, fee=None, outcome=None):
    _n[0] += 1
    o = Order(external_id=f"TEST-PRORD-{_n[0]}", customer_id=c.id, order_date=day, order_value=D(value), products=products, sales_channel=channel, payment_type=payment, city="Lahore", outcome=outcome, source="manual")
    db.add(o)
    db.flush()
    if status:
        db.add(Shipment(external_id=f"TEST-PRSHIP-{_n[0]}", order_id=o.id, customer_id=c.id, courier="TCS", city="Lahore", booked_date=day, closed_date=day, status=status, courier_fee=fee))
        db.flush()
    return o


def test_the_whole_picture_for_a_small_shop(db_session):
    db_session.add(StockItem(sku="TST-SH", name="Test shoes", cost_price=D(1000), stock=2, reorder_threshold=5))
    pa.get_settings(db_session).packing_cost = D(50)
    pa.get_settings(db_session).return_shipping_cost = D(150)
    db_session.add(AdSpend(spend_date=TODAY, channel="instagram", amount=D(300), source="manual"))
    c = customer(db_session)
    order(db_session, c, status="delivered", fee=D(200), payment="prepaid")
    order(db_session, c, status="returned", fee=D(200))
    order(db_session, c, products="Mystery item", status="delivered", fee=D(200))             # not in inventory: cost unknown
    order(db_session, c)                                                                      # still on the way
    a = pa.analyze(db_session, TODAY, TODAY)
    assert (a.placed, a.ended, a.pending, a.counted, a.cost_unknown) == (4, 3, 1, 2, 1)
    assert a.gross_revenue == D(10000) and a.delivered_revenue == D(5000) and a.prepaid_collected == D(2500)
    assert a.ad_spend == D(300) and a.low_stock == 1
    # ad cost: 300 spread over the channel's 4 orders = 75 each (pending orders carry none, so each ended order carries 75)
    delivered = 2500 - 1000 - 50 - 200 - 75
    returned = -(50 + 200 + 150 + 75)
    assert a.profit == D(delivered + returned)
    assert a.return_rate is None                                                              # too few orders for a rate


def test_nothing_is_invented_when_no_costs_were_entered(db_session):
    c = customer(db_session)
    order(db_session, c, status="delivered", fee=None)
    a = pa.analyze(db_session, TODAY, TODAY)
    assert a.counted == 0 and a.cost_unknown == 1 and a.profit == 0
    assert a.missing == {"packing": 1, "courier_fee": 1, "product_cost": 1}


def test_the_period_uses_karachi_days(db_session):
    from datetime import datetime, timezone

    just_after_midnight_karachi = datetime(2026, 3, 9, 20, 30, tzinfo=timezone.utc)           # 01:30 on the 10th in Pakistan
    assert pa.today_karachi(just_after_midnight_karachi) == date(2026, 3, 10)
    start, end = pa.default_range(just_after_midnight_karachi, days=30)
    assert end == date(2026, 3, 10) and (end - start).days == 29


def test_api_summary_settings_and_ad_spend(db_client, db_session):
    c = customer(db_session)
    order(db_session, c, status="delivered", fee=D(200), day=date.today())
    db_session.commit()
    assert db_client.put("/api/v1/profit/settings", json={"packingCost": 50, "returnShippingCost": 150}).json()["packingCost"] == 50
    added = db_client.post("/api/v1/profit/ad-spend", json={"spendDate": str(date.today()), "channel": "instagram", "amount": 500, "campaign": "Eid"})
    assert added.status_code == 201
    body = db_client.get("/api/v1/profit/summary").json()
    assert body["orders"]["placed"] == 1 and body["money"]["adSpend"] == 500.0 and body["packingSet"] is True and body["minGroupCount"] == 20
    assert body["money"]["estimatedProfit"] is None                                           # the only order has an unknown product cost
    assert any(d["name"] == "Real profit per order" for d in body["definitions"])
    assert db_client.get("/api/v1/profit/summary?start=2026-03-10&end=2026-03-01").status_code == 422
    assert db_client.get(f"/api/v1/profit/summary?start=2020-01-01&end={date.today()}").status_code == 422
    assert db_client.post("/api/v1/profit/ad-spend", json={"spendDate": "2026-03-10", "channel": "tiktok", "amount": 5}).status_code == 422
    assert db_client.delete(f"/api/v1/profit/ad-spend/{added.json()['id']}").status_code == 204
    assert db_client.get("/api/v1/profit/ad-spend").json() == []


def test_staff_cannot_change_the_cost_settings_or_delete_spend(db_client):
    from types import SimpleNamespace
    import uuid

    from app.api.deps import require_user
    from app.main import app

    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=uuid.uuid4(), email="staff@test.example", name="S", role="staff")
    assert db_client.put("/api/v1/profit/settings", json={"packingCost": 1}).status_code == 403
    assert db_client.delete("/api/v1/profit/ad-spend/1").status_code == 403
    assert db_client.post("/api/v1/profit/ad-spend", json={"spendDate": "2026-03-10", "channel": "instagram", "amount": 5}).status_code == 201
