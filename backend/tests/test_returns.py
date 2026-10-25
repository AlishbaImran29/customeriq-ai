"""Returns, refunds and tickets: the flow, stock rules, "the app never moves money", evidence checks, messages.
Customers, orders and files are made up (marked TEST); nothing is sent and no storage is used."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import Message, Order
from app.models.inventory import StockItem
from app.models.returns import Refund, ReturnEvent, Ticket
from app.services import inventory, returns as service
from tests.test_order_status import make_customer, make_order, make_template, opt_in

NOW = datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 64


def settings(**kw) -> Settings:
    return Settings(_env_file=None, messaging_dry_run=True, **kw)


def setup_order(db, value=2500, products="Test lip balm x2"):
    customer = make_customer(db)
    return customer, make_order(db, customer, value=value, products=products)


def test_one_open_return_per_order(db_session):
    _, order = setup_order(db_session)
    ret = service.request_return(db_session, order.id, "Wrong size", "seller@test.example")
    assert ret.status == "requested" and db_session.query(ReturnEvent).filter_by(return_id=ret.id, event="requested").one().by == "seller@test.example"
    with pytest.raises(ApiError) as caught:
        service.request_return(db_session, order.id, "Again")
    assert caught.value.code == "return_exists"
    with pytest.raises(ApiError):
        service.request_return(db_session, 999999, "No such order")


def test_approve_with_refund_asks_for_a_refund_and_never_moves_money(db_session):
    _, order = setup_order(db_session, value=2500)
    ret = service.request_return(db_session, order.id, "Damaged")
    service.approve(db_session, settings(), ret, "refund", amount=Decimal("1000"), by="seller@test.example", now=NOW)
    refund = db_session.query(Refund).one()
    assert (ret.status, ret.resolution, refund.status, refund.amount) == ("approved", "refund", "requested", Decimal("1000"))
    assert refund.recorded_at is None and refund.method is None                                # nothing was paid: it is only a note to self
    with pytest.raises(ApiError) as caught:
        service.approve(db_session, settings(), ret, "refund")
    assert caught.value.code == "not_requested"


def test_a_refund_cannot_be_more_than_the_order(db_session):
    _, order = setup_order(db_session, value=2500)
    ret = service.request_return(db_session, order.id, "Damaged")
    with pytest.raises(ApiError) as caught:
        service.approve(db_session, settings(), ret, "refund", amount=Decimal("2500.01"))
    assert caught.value.code == "invalid_amount" and ret.status == "requested"                 # nothing changed


def test_the_seller_records_a_refund_they_paid_and_it_can_only_be_recorded_once(db_session):
    _, order = setup_order(db_session)
    ret = service.request_return(db_session, order.id, "Damaged")
    service.approve(db_session, settings(), ret, "refund", now=NOW)
    refund = db_session.query(Refund).one()
    with pytest.raises(ApiError) as caught:
        service.record_refund(db_session, settings(), refund, "  ", None)
    assert caught.value.code == "method_required"
    service.record_refund(db_session, settings(), refund, "JazzCash", "TX-123", by="seller@test.example", now=NOW)
    assert (refund.status, refund.method, refund.reference, refund.recorded_by) == ("recorded", "JazzCash", "TX-123", "seller@test.example")
    with pytest.raises(ApiError):
        service.record_refund(db_session, settings(), refund, "JazzCash", None)
    assert [e.event for e in db_session.query(ReturnEvent).filter_by(return_id=ret.id).order_by(ReturnEvent.id)] == ["requested", "refund_requested", "approved", "refund_recorded"]


def test_reject_closes_the_door_on_further_steps(db_session):
    _, order = setup_order(db_session)
    ret = service.request_return(db_session, order.id, "Changed my mind")
    service.reject(db_session, settings(), ret, "Outside the 7 day window", now=NOW)
    assert ret.status == "rejected" and ret.decision_note == "Outside the 7 day window"
    with pytest.raises(ApiError):
        service.receive(db_session, ret, True)


def test_a_replacement_makes_a_new_order_that_reserves_stock(db_session):
    item = StockItem(sku="TST-R", name="Test lip balm", stock=10)
    db_session.add(item)
    db_session.flush()
    _, order = setup_order(db_session, products="Test lip balm x2")
    ret = service.request_return(db_session, order.id, "Broken")
    service.approve(db_session, settings(), ret, "replacement", now=NOW)
    replacement = db_session.get(Order, ret.replacement_order_id)
    assert replacement.external_id.startswith("REPL-") and replacement.order_value == 0 and replacement.customer_id == order.customer_id
    assert (item.stock, item.reserved) == (10, 2)                                              # the replacement is reserved like any order


def test_received_goods_stay_off_the_shelf_unless_the_seller_says_so(db_session):
    item = StockItem(sku="TST-S", name="Test lip balm", stock=10)
    db_session.add(item)
    db_session.flush()
    _, order = setup_order(db_session, products="Test lip balm x2")
    inventory.sell_order(db_session, order)                                                   # it was shipped: stock 8
    ret = service.request_return(db_session, order.id, "Not needed")
    service.approve(db_session, settings(), ret, "none", now=NOW)
    service.receive(db_session, ret, restock=False, now=NOW)
    assert item.stock == 8 and ret.restocked is False
    with pytest.raises(ApiError):
        service.request_return(db_session, order.id, "Again")                                  # a received return is still open until it is closed
    inventory.restock_order(db_session, order)
    inventory.restock_order(db_session, order)                                                 # restocking twice puts the goods back once
    assert item.stock == 10


def test_restock_puts_sold_items_back(db_session):
    item = StockItem(sku="TST-T", name="Test lip balm", stock=10)
    db_session.add(item)
    db_session.flush()
    _, order = setup_order(db_session, products="Test lip balm x2")
    inventory.sell_order(db_session, order)
    ret = service.request_return(db_session, order.id, "Not needed")
    service.approve(db_session, settings(), ret, "none", now=NOW)
    service.receive(db_session, ret, restock=True, now=NOW)
    assert item.stock == 10 and ret.restocked is True


def test_a_return_cannot_be_closed_before_receipt_or_with_an_open_refund(db_session):
    _, order = setup_order(db_session)
    ret = service.request_return(db_session, order.id, "Damaged")
    service.approve(db_session, settings(), ret, "refund", now=NOW)
    with pytest.raises(ApiError) as caught:
        service.close(db_session, ret)
    assert caught.value.code == "not_received"
    service.receive(db_session, ret, restock=False, now=NOW)
    with pytest.raises(ApiError) as caught:
        service.close(db_session, ret)
    assert caught.value.code == "refund_pending"
    service.record_refund(db_session, settings(), db_session.query(Refund).one(), "Bank transfer", None, now=NOW)
    assert service.close(db_session, ret).status == "closed"


def test_the_customer_is_told_only_if_they_agreed_and_a_template_is_approved(db_session):
    customer, order = setup_order(db_session)
    opt_in(db_session, customer)
    make_template(db_session, "return_approved", body="Hi {{first_name}}, return for {{order_number}} approved.")
    ret = service.request_return(db_session, order.id, "Damaged")
    service.approve(db_session, settings(), ret, "none", now=NOW)
    message = db_session.query(Message).one()
    assert "approved" in message.rendered_text and message.status in ("sent", "queued")


def test_evidence_checks_type_size_and_real_content():
    assert service.check_evidence(PNG, "image/png") == "image"
    assert service.check_evidence(MP4, "video/mp4") == "video"
    for content, mime, code in [(PNG, "application/pdf", "file_type"), (b"not a picture" * 10, "image/png", "not_really_image"), (b"0" * 64, "video/mp4", "not_really_video"),
                                (PNG + b"0" * (4 * 1024 * 1024), "image/png", "too_large")]:
        with pytest.raises(ApiError) as caught:
            service.check_evidence(content, mime)
        assert caught.value.code == code


def test_ticket_status_rules(db_session):
    ticket = Ticket(subject="Test complaint")
    db_session.add(ticket)
    db_session.flush()
    service.move_ticket(ticket, "in_progress")
    service.move_ticket(ticket, "resolved", NOW)
    assert ticket.resolved_at == NOW
    with pytest.raises(ApiError):
        service.move_ticket(ticket, "in_progress")                                            # a resolved ticket is reopened first
    service.move_ticket(ticket, "open")
    assert ticket.resolved_at is None
    with pytest.raises(ApiError):
        service.move_ticket(ticket, "open")


def test_default_return_templates_exist_in_both_languages(db_session):
    from app.services.messaging import defaults

    rows = defaults.default_templates(["returns"])
    assert len(rows) == 12 and {r["event"] for r in rows} == {"return_approved", "return_rejected", "refund_recorded"}


# --- over HTTP ------------------------------------------------------------------------------------------------------------------------


def test_api_full_return_flow(db_client, db_session):
    _, order = setup_order(db_session, value=3000)
    db_session.commit()
    r = db_client.post("/api/v1/returns", json={"orderId": order.id, "reason": "Wrong colour"})
    assert r.status_code == 201 and r.json()["status"] == "requested" and r.json()["events"][0]["event"] == "requested"
    rid = r.json()["id"]
    assert db_client.post("/api/v1/returns", json={"orderId": order.id, "reason": "Again"}).status_code == 409
    assert db_client.post(f"/api/v1/returns/{rid}/receive", json={"restock": True}).status_code == 409                 # not approved yet
    approved = db_client.post(f"/api/v1/returns/{rid}/approve", json={"resolution": "refund", "amount": 1500})
    assert approved.status_code == 200 and approved.json()["refunds"][0]["status"] == "requested" and approved.json()["refunds"][0]["amount"] == 1500.0
    refund_id = approved.json()["refunds"][0]["id"]
    assert db_client.post(f"/api/v1/returns/{rid}/receive", json={"restock": False}).json()["status"] == "received"
    assert db_client.post(f"/api/v1/returns/{rid}/close").status_code == 409                                              # refund not recorded yet
    recorded = db_client.post(f"/api/v1/refunds/{refund_id}/record", json={"method": "JazzCash", "reference": "TX1"})
    assert recorded.status_code == 200 and recorded.json()["status"] == "recorded"
    assert db_client.post(f"/api/v1/returns/{rid}/close").json()["status"] == "closed"
    assert db_client.get("/api/v1/refunds?status=recorded").json()[0]["method"] == "JazzCash"
    assert [e["event"] for e in db_client.get(f"/api/v1/returns/{rid}").json()["events"]][0] == "closed"


def test_api_evidence_needs_storage_and_checks_the_file(db_client, db_session, monkeypatch):
    from app.services import supabase_storage

    _, order = setup_order(db_session)
    db_session.commit()
    rid = db_client.post("/api/v1/returns", json={"orderId": order.id, "reason": "Damaged"}).json()["id"]
    bad = db_client.post(f"/api/v1/returns/{rid}/evidence", files={"file": ("x.png", b"not a picture", "image/png")})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "not_really_image"
    stored = []
    monkeypatch.setattr(supabase_storage, "put_object", lambda s, bucket, path, content, mime: stored.append((bucket, path)))
    ok = db_client.post(f"/api/v1/returns/{rid}/evidence", files={"file": ("../../evil name.png", PNG, "image/png")})
    assert ok.status_code == 201 and stored[0][0] == "return-evidence" and "evil" not in stored[0][1] and stored[0][1].startswith(f"returns/{rid}/")
    assert len(db_client.get(f"/api/v1/returns/{rid}").json()["evidence"]) == 1


def test_api_tickets(db_client, db_session):
    customer, order = setup_order(db_session)
    db_session.commit()
    created = db_client.post("/api/v1/tickets", json={"subject": "Parcel arrived open", "body": "Photo sent on WhatsApp", "customerId": customer.id, "orderId": order.id, "priority": "high"})
    assert created.status_code == 201 and created.json()["status"] == "open"
    tid = created.json()["id"]
    assert db_client.patch(f"/api/v1/tickets/{tid}", json={"status": "in_progress", "assignedTo": "staff@test.example"}).json()["assignedTo"] == "staff@test.example"
    noted = db_client.post(f"/api/v1/tickets/{tid}/notes", json={"text": "Called the courier"})
    assert noted.status_code == 201 and noted.json()["notes"][0]["text"] == "Called the courier"
    assert db_client.patch(f"/api/v1/tickets/{tid}", json={"status": "open"}).status_code == 200
    assert db_client.patch(f"/api/v1/tickets/{tid}", json={"status": "open"}).status_code == 409
    assert db_client.post("/api/v1/tickets", json={"subject": "Ghost", "customerId": 999999}).status_code == 404
    assert [t["id"] for t in db_client.get("/api/v1/tickets?status=open").json()] == [tid]
