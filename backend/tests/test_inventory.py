"""Simple inventory: parsing order items, reserve / sell / release / restock, and "never changes the stock twice".
Everything is made up for the tests (marked TEST)."""

import pytest

from app.models.inventory import StockItem, StockMovement
from app.services import inventory as inv
from tests.test_order_status import NOON, make_customer, make_order, record


def item(db, sku="TST-1", name="Test lip balm", stock=10, threshold=2):
    row = StockItem(sku=sku, name=name, stock=stock, reorder_threshold=threshold)
    db.add(row)
    db.flush()
    return row


def test_parse_lines_reads_names_and_quantities():
    assert inv.parse_lines("Lip balm, Hair oil x2") == [("Lip balm", 1), ("Hair oil", 2)]
    assert inv.parse_lines("3x Soap; Candle ×4\nBag") == [("Soap", 3), ("Candle", 4), ("Bag", 1)]
    assert inv.parse_lines(None) == [] and inv.parse_lines(" , ") == []


def test_items_are_matched_by_sku_or_name_and_unknown_parts_are_ignored(db_session):
    a, b = item(db_session, "TST-A", "Test soap"), item(db_session, "TST-B", "Test candle")
    order = make_order(db_session, make_customer(db_session), products="test soap x2, TST-B, Something not counted")
    assert inv.order_items(db_session, order) == {a.id: 2, b.id: 1}


def test_confirmed_reserves_and_dispatched_sells(db_session):
    row = item(db_session)
    order = make_order(db_session, make_customer(db_session), products="Test lip balm x3")
    record(db_session, order, "confirmed", notify=False)
    assert (row.stock, row.reserved) == (10, 3) and inv.available(row) == 7
    record(db_session, order, "dispatched", notify=False)
    assert (row.stock, row.reserved) == (7, 0)


def test_the_same_event_never_changes_the_stock_twice(db_session):
    row = item(db_session)
    order = make_order(db_session, make_customer(db_session), products="Test lip balm x2")
    inv.reserve_order(db_session, order)
    inv.reserve_order(db_session, order)
    assert row.reserved == 2
    inv.sell_order(db_session, order)
    again = inv.sell_order(db_session, order)
    inv.on_status(db_session, order, "delivered")        # a later status must not sell a second time either
    assert (row.stock, row.reserved) == (8, 0)
    assert again[0].applied is False
    assert db_session.query(StockMovement).filter(StockMovement.kind == "sale").count() == 1


def test_selling_an_order_that_was_never_reserved_still_takes_stock(db_session):
    row = item(db_session)
    order = make_order(db_session, make_customer(db_session), products="Test lip balm")
    inv.sell_order(db_session, order)
    assert (row.stock, row.reserved) == (9, 0)


def test_oversold_is_reported_not_hidden(db_session):
    row = item(db_session, stock=1)
    order = make_order(db_session, make_customer(db_session), products="Test lip balm x3")
    effect = inv.reserve_order(db_session, order)[0]
    assert effect.short_by == 2 and inv.available(row) == -2 and inv.is_low(row)


def test_release_gives_the_reservation_back_but_not_after_a_sale(db_session):
    row = item(db_session)
    customer = make_customer(db_session)
    cancelled = make_order(db_session, customer, products="Test lip balm x2")
    inv.reserve_order(db_session, cancelled)
    inv.release_order(db_session, cancelled)
    inv.release_order(db_session, cancelled)             # pressing the button twice changes nothing
    assert (row.stock, row.reserved) == (10, 0)
    sold = make_order(db_session, customer, products="Test lip balm")
    inv.reserve_order(db_session, sold)
    inv.sell_order(db_session, sold)
    assert inv.release_order(db_session, sold) == []
    assert (row.stock, row.reserved) == (9, 0)


def test_restock_only_returns_what_was_sold_and_only_once(db_session):
    row = item(db_session)
    customer = make_customer(db_session)
    never_sold = make_order(db_session, customer, products="Test lip balm")
    assert inv.restock_order(db_session, never_sold) == []
    order = make_order(db_session, customer, products="Test lip balm x2")
    inv.sell_order(db_session, order)
    inv.restock_order(db_session, order)
    inv.restock_order(db_session, order)
    assert row.stock == 10


def test_old_statuses_do_not_touch_the_stock(db_session):
    from datetime import timedelta

    row = item(db_session)
    order = make_order(db_session, make_customer(db_session), products="Test lip balm")
    record(db_session, order, "dispatched", notify=False, at=NOON - timedelta(days=20))
    assert row.stock == 10


def test_adjust_rules(db_session):
    row = item(db_session)
    inv.adjust(db_session, row.id, 5, "receive", "new box")
    inv.adjust(db_session, row.id, -3, "adjustment", "damaged")
    assert row.stock == 12
    with pytest.raises(Exception):
        inv.adjust(db_session, row.id, 0, "adjustment", None)
    with pytest.raises(Exception):
        inv.adjust(db_session, row.id, -1, "receive", None)


def test_api_add_adjust_list_and_low_stock(db_client):
    r = db_client.post("/api/v1/inventory/items", json={"sku": "tst-9", "name": "Test mug", "stock": 5, "reorderThreshold": 5})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sku"] == "TST-9" and body["stock"] == 5 and body["low"] is True
    assert db_client.post("/api/v1/inventory/items", json={"sku": "TST-9", "name": "Dup"}).status_code == 409
    r = db_client.post(f"/api/v1/inventory/items/{body['id']}/adjust", json={"delta": 20, "kind": "receive", "note": "restock"})
    assert r.json()["stock"] == 25 and r.json()["low"] is False
    assert db_client.post(f"/api/v1/inventory/items/{body['id']}/adjust", json={"delta": 0}).status_code in (422,)
    moves = db_client.get(f"/api/v1/inventory/items/{body['id']}/movements").json()
    assert [m["kind"] for m in moves] == ["receive", "receive"]          # opening stock, then the delivery
    assert db_client.get("/api/v1/inventory/items?lowOnly=true").json() == []
    assert db_client.patch(f"/api/v1/inventory/items/{body['id']}", json={"status": "archived"}).json()["status"] == "archived"
