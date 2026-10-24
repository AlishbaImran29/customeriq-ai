"""Auto Messenger part 2: order status history, the customer messages it causes, default templates, the Shopify
webhook and the courier-file hook. Everything is made up for the tests (marked TEST)."""

import base64
import hashlib
import hmac
import io
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.config import Settings, get_settings
from app.main import app
from app.models import Customer, Message, MessageTemplate, Order, OrderStatusHistory, Shipment
from app.services import order_status, shopify_hooks
from app.services.messaging import consent, defaults
from app.services.messaging.render import check_template_text
from app.services.messaging.settings_store import get_row

NOON = datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc)          # 12:00 in Pakistan: not in quiet hours
SHOPIFY_SECRET = "test-shopify-secret"
_n = [0]


def settings(**changes) -> Settings:
    return Settings(_env_file=None, messaging_dry_run=True, **changes)


def make_customer(db, *, phone="+923001234567", email="test.customer@testcustomer.test", name="Test Ali", language=None):
    _n[0] += 1
    c = Customer(external_id=f"TEST-OS{_n[0]}", first_name=name, phone=phone, phone_normalised=phone, email=email, country="Pakistan", preferred_language=language)
    db.add(c)
    db.flush()
    return c


def make_order(db, customer, *, payment="cod", value=2500, products="Test shoes", external_id=None, note=None):
    _n[0] += 1
    o = Order(external_id=external_id or f"TEST-ORD-{_n[0]}", customer_id=customer.id, order_date=date(2026, 3, 9), order_value=Decimal(value),
              payment_type=payment, products=products, note=note, source="manual")
    db.add(o)
    db.flush()
    return o


def make_template(db, event, channel="whatsapp", language="en", body=None, approved=True, category="utility"):
    _n[0] += 1
    t = MessageTemplate(
        name=f"test_{event}_{channel}_{language}_{_n[0]}", channel=channel, category=category, language=language, event=event,
        subject="TEST {{order_number}}" if channel == "email" else None,
        body=body or "Hi {{first_name}}, order {{order_number}} ({{items}}) total {{amount}}. {{cod_note}} {{tracking_line}}", approved_by_seller=approved,
    )
    db.add(t)
    db.flush()
    return t


def always_open(db):
    """Quiet hours off for a test that goes over HTTP (it uses the real clock, which must not matter)."""
    from datetime import time

    row = get_row(db)
    row.quiet_start, row.quiet_end = time(23, 59, 59), time(0, 0)


def opt_in(db, customer, channel="whatsapp"):
    consent.set_consent(db, customer.id, channel, True, "manual")


def record(db, order, status, **kw):
    kw.setdefault("source", "manual")
    kw.setdefault("now", NOON)
    kw.setdefault("at", NOON)
    return order_status.record_status(db, settings(), order, status, **kw)


# --- the rules ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("previous,new,forward", [
    (None, "confirmed", True), (None, "delivered", True), ("confirmed", "dispatched", True), ("dispatched", "in_transit", True),
    ("in_transit", "out_for_delivery", True), ("out_for_delivery", "delivered", True), ("dispatched", "returned", True), ("delivered", "returned", True),
    ("dispatched", "confirmed", False), ("delivered", "in_transit", False), ("in_transit", "in_transit", False), ("returned", "delivered", False),
    ("returned", "returned", False),
])
def test_is_forward(previous, new, forward):
    assert order_status.is_forward(previous, new) is forward


def test_an_unknown_status_is_refused(db_session):
    from app.core.errors import ApiError

    order = make_order(db_session, make_customer(db_session))
    with pytest.raises(ApiError):
        record(db_session, order, "teleported")


# --- history ----------------------------------------------------------------------------------------------------------------


def test_the_latest_row_is_the_current_status_and_the_same_status_adds_nothing(db_session):
    order = make_order(db_session, make_customer(db_session))
    first = record(db_session, order, "confirmed")
    again = record(db_session, order, "confirmed", courier="TCS", tracking="TRK-1")
    assert first.recorded and not again.recorded and again.reason == "same_status"
    assert order_status.latest_status(db_session, order.id).tracking_number == "TRK-1"                  # a later tracking number is remembered
    record(db_session, order, "dispatched", at=NOON + timedelta(hours=1))
    assert order_status.latest_status(db_session, order.id).status == "dispatched"
    assert db_session.query(OrderStatusHistory).filter_by(order_id=order.id).count() == 2


def test_going_backwards_is_recorded_but_never_announced(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    order = make_order(db_session, customer)
    make_template(db_session, "order_confirmed")
    record(db_session, order, "in_transit")
    back = record(db_session, order, "confirmed", at=NOON + timedelta(hours=1))
    assert back.recorded and not back.announced and back.reason == "not_forward" and back.messages == []


def test_an_old_status_is_recorded_but_does_not_message_anyone(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    order = make_order(db_session, customer)
    make_template(db_session, "order_delivered")
    old = record(db_session, order, "delivered", at=NOON - timedelta(days=4))
    assert old.recorded and not old.announced and old.reason == "too_old" and db_session.query(Message).count() == 0
    fresh_order = make_order(db_session, customer)
    assert record(db_session, fresh_order, "delivered", at=NOON - timedelta(days=2)).announced is True        # 2 days old: still news


def test_notify_false_records_without_messaging(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    order = make_order(db_session, customer)
    make_template(db_session, "order_confirmed")
    quiet = record(db_session, order, "confirmed", notify=False)
    assert quiet.recorded and quiet.reason == "not_requested" and db_session.query(Message).count() == 0


# --- the messages ---------------------------------------------------------------------------------------------------------------


def test_a_dispatch_message_has_the_order_courier_tracking_and_the_cod_note(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    order = make_order(db_session, customer, payment="cod", value=2500)
    make_template(db_session, "order_dispatched")
    change = record(db_session, order, "dispatched", courier="TCS", tracking="TRK123")
    message = change.messages[0]
    assert change.announced and message.status == "sent" and message.dry_run is True and message.order_id == order.id
    assert message.rendered_text == "Hi Test Ali, order " + order.external_id + " (Test shoes) total Rs 2,500. Please keep Rs 2,500 ready. Courier: TCS, tracking number: TRK123."


def test_prepaid_orders_get_no_cod_note_and_missing_courier_leaves_the_line_out(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    order = make_order(db_session, customer, payment="prepaid")
    make_template(db_session, "order_dispatched")
    text = record(db_session, order, "dispatched").messages[0].rendered_text
    assert "keep" not in text and "Courier" not in text and text.endswith("total Rs 2,500.")


def test_the_cod_note_is_only_for_orders_that_are_still_on_their_way(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    order = make_order(db_session, customer, payment="cod")
    make_template(db_session, "order_delivered")
    assert "keep" not in record(db_session, order, "delivered").messages[0].rendered_text


def test_the_customers_language_is_used_with_the_shops_default_as_the_fallback(db_session):
    urdu = make_customer(db_session, language="ur")
    plain = make_customer(db_session, phone="+923009999999", email="b.test@testcustomer.test")
    for c in (urdu, plain):
        opt_in(db_session, c)
    make_template(db_session, "order_confirmed", language="en", body="EN {{first_name}} {{order_number}}")
    make_template(db_session, "order_confirmed", language="ur", body="UR {{first_name}} {{order_number}}")
    assert record(db_session, make_order(db_session, urdu), "confirmed").messages[0].rendered_text.startswith("UR ")
    assert record(db_session, make_order(db_session, plain), "confirmed").messages[0].rendered_text.startswith("EN ")           # default language is English
    get_row(db_session).default_language = "ur"
    other = make_customer(db_session, phone="+923008888888", email="c.test@testcustomer.test")
    opt_in(db_session, other)
    assert record(db_session, make_order(db_session, other), "confirmed").messages[0].rendered_text.startswith("UR ")


def test_both_channels_are_used_where_the_customer_agreed(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    opt_in(db_session, customer, "email")
    make_template(db_session, "order_confirmed")
    make_template(db_session, "order_confirmed", channel="email")
    change = record(db_session, make_order(db_session, customer), "confirmed")
    assert sorted((m.channel, m.status) for m in change.messages) == [("email", "sent"), ("whatsapp", "sent")]
    assert next(m for m in change.messages if m.channel == "email").subject.startswith("TEST ")


def test_no_consent_no_template_or_an_unapproved_template_means_no_message(db_session):
    customer = make_customer(db_session)
    order = make_order(db_session, customer)
    assert record(db_session, order, "confirmed").messages == []                                                # no template at all
    make_template(db_session, "order_dispatched")
    skipped = record(db_session, order, "dispatched").messages[0]
    assert (skipped.status, skipped.error) == ("skipped", "no_consent")
    opt_in(db_session, customer)
    make_template(db_session, "order_in_transit", approved=False)
    assert record(db_session, order, "in_transit").messages[0].error == "template_not_approved"


def test_an_approved_template_is_preferred_over_an_unapproved_one(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    make_template(db_session, "order_confirmed", approved=False, body="DRAFT {{first_name}} {{order_number}}")
    make_template(db_session, "order_confirmed", approved=True, body="FINAL {{first_name}} {{order_number}}")
    assert record(db_session, make_order(db_session, customer), "confirmed").messages[0].rendered_text.startswith("FINAL")


def test_each_status_of_an_order_is_announced_only_once(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    order = make_order(db_session, customer)
    make_template(db_session, "order_dispatched")
    record(db_session, order, "dispatched")
    record(db_session, order, "in_transit", at=NOON + timedelta(hours=1))
    record(db_session, order, "dispatched", at=NOON + timedelta(hours=2))                                      # set again: a step back
    assert db_session.query(Message).filter_by(order_id=order.id).count() == 1


def test_quiet_hours_hold_order_messages_but_out_for_delivery_may_go_from_8(db_session):
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    make_template(db_session, "order_dispatched", body="Dispatched {{order_number}}")
    make_template(db_session, "order_out_for_delivery", body="Out today {{order_number}}")
    early = datetime(2026, 3, 10, 3, 30, tzinfo=timezone.utc)                                                   # 08:30 in Pakistan
    a, b = make_order(db_session, customer), make_order(db_session, customer)
    assert record(db_session, a, "dispatched", at=early, now=early).messages[0].status == "queued"
    assert record(db_session, b, "out_for_delivery", at=early, now=early).messages[0].status == "sent"
    night = datetime(2026, 3, 10, 17, 30, tzinfo=timezone.utc)                                                  # 22:30 in Pakistan
    c = make_order(db_session, customer)
    held = record(db_session, c, "out_for_delivery", at=night, now=night).messages[0]
    assert held.status == "queued" and held.next_attempt_at == datetime(2026, 3, 11, 3, 0, tzinfo=timezone.utc)      # tomorrow 08:00 in Pakistan


def test_a_shopify_order_shows_the_shops_own_number(db_session):
    order = make_order(db_session, make_customer(db_session), external_id="SHOPIFY-450789469", note="Shopify order #1001")
    assert order_status.order_number(order) == "#1001"
    assert order_status.order_number(make_order(db_session, make_customer(db_session, phone=None), external_id="TEST-PLAIN")) == "TEST-PLAIN"


# --- default templates -------------------------------------------------------------------------------------------------------------


def test_every_default_template_is_valid_in_both_languages_and_unapproved(db_session):
    rows = defaults.default_templates()
    assert {r["language"] for r in rows} == {"en", "ur"} and {r["channel"] for r in rows} == {"whatsapp", "email"}
    for r in rows:
        check_template_text(r["body"], r["subject"])
        assert (r["channel"] == "email") == bool(r["subject"])
    events = {r["event"] for r in rows}
    assert {f"order_{s}" for s in defaults.ORDER_EVENTS} <= events and {"delivered_unboxing", "media_share_question", "review_request"} <= events
    assert defaults.seed_defaults(db_session) == len(rows)
    assert db_session.query(MessageTemplate).filter_by(approved_by_seller=True).count() == 0
    assert defaults.seed_defaults(db_session) == 0                                                                  # nothing added twice


def test_seeding_never_overwrites_an_edited_template(db_session):
    defaults.seed_defaults(db_session, ["orders"])
    row = db_session.query(MessageTemplate).filter_by(name="order_dispatched_en").one()
    row.body = "My own wording {{order_number}}"
    defaults.seed_defaults(db_session, ["orders"])
    assert db_session.query(MessageTemplate).filter_by(name="order_dispatched_en").one().body == "My own wording {{order_number}}"


def test_the_default_whatsapp_templates_can_be_used_once_approved(db_session):
    defaults.seed_defaults(db_session, ["orders"])
    for t in db_session.query(MessageTemplate).filter_by(channel="whatsapp", language="en"):
        t.approved_by_seller = True
    get_row(db_session).store_name = "Test Boutique"
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    order = make_order(db_session, customer, payment="cod")
    text = record(db_session, order, "out_for_delivery", courier="Leopards", tracking="LP-9").messages[0].rendered_text
    assert text.startswith("Hello Test Ali, your order " + order.external_id + " is out for delivery today.") and "Rs 2,500 ready" in text and "Leopards" in text


# --- the board and the manual button (HTTP) ------------------------------------------------------------------------------------------


def test_the_board_the_manual_button_and_the_timeline(db_client, db_session):
    app.dependency_overrides[get_settings] = lambda: settings()
    always_open(db_session)
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    order = make_order(db_session, customer)
    make_template(db_session, "order_dispatched")
    board = db_client.get("/api/v1/messaging/orders").json()
    assert board[0]["id"] == order.id and board[0]["status"] is None and board[0]["messages"] == 0 and board[0]["customerName"] == "Test Ali"

    done = db_client.post(f"/api/v1/messaging/orders/{order.id}/status", json={"status": "dispatched", "courier": "TCS", "trackingNumber": "TRK9"}).json()
    assert done["recorded"] and done["announced"] and done["messages"][0]["status"] == "sent" and "TRK9" in done["messages"][0]["text"]
    again = db_client.post(f"/api/v1/messaging/orders/{order.id}/status", json={"status": "dispatched"}).json()
    assert again["recorded"] is False and again["reason"] == "same_status"
    assert db_client.post(f"/api/v1/messaging/orders/{order.id}/status", json={"status": "teleported"}).status_code == 422
    assert db_client.post("/api/v1/messaging/orders/999999/status", json={"status": "delivered"}).status_code == 404

    board = db_client.get(f"/api/v1/messaging/orders?search=ali").json()
    assert board[0]["status"] == "dispatched" and board[0]["messages"] == 1
    assert db_client.get("/api/v1/messaging/orders?search=nobody-here").json() == []
    timeline = db_client.get(f"/api/v1/messaging/orders/{order.id}/timeline").json()
    assert [e["status"] for e in timeline["events"]] == ["dispatched"] and timeline["events"][0]["courier"] == "TCS" and len(timeline["messages"]) == 1
    silent = db_client.post(f"/api/v1/messaging/orders/{order.id}/status", json={"status": "delivered", "notify": False}).json()
    assert silent["recorded"] and not silent["announced"] and silent["reason"] == "not_requested"


def test_seed_defaults_endpoint(db_client):
    added = db_client.post("/api/v1/messaging/templates/seed-defaults", json={"groups": ["orders"]}).json()["added"]
    assert added == 24
    assert db_client.post("/api/v1/messaging/templates/seed-defaults", json={"groups": ["orders"]}).json()["added"] == 0
    assert db_client.post("/api/v1/messaging/templates/seed-defaults", json={}).json()["added"] == 10
    assert db_client.post("/api/v1/messaging/templates/seed-defaults", json={"groups": ["spam"]}).status_code == 422


# --- Shopify ---------------------------------------------------------------------------------------------------------------------------


def shopify_headers(body: bytes, topic: str, webhook_id: str, secret=SHOPIFY_SECRET, shop="test-shop.myshopify.com"):
    digest = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return {"X-Shopify-Hmac-Sha256": digest, "X-Shopify-Topic": topic, "X-Shopify-Webhook-Id": webhook_id, "X-Shopify-Shop-Domain": shop, "Content-Type": "application/json"}


ORDER_PAYLOAD = {
    "id": 450789469, "order_number": 1001, "name": "#1001", "created_at": "2026-03-10T09:00:00+05:00", "total_price": "2500.00", "email": "ali.test@testcustomer.test",
    "payment_gateway_names": ["Cash on Delivery (COD)"],
    "customer": {"id": 7001, "first_name": "Test", "last_name": "Ali", "accepts_marketing": True, "phone": "0300 1234567"},
    "shipping_address": {"city": "Lahore", "phone": "0300 1234567", "country": "Pakistan"},
    "line_items": [{"title": "Test shoes", "quantity": 2}, {"title": "Test bag", "quantity": 1}],
}


def post_shopify(db_client, payload, topic, webhook_id, **kw):
    body = json.dumps(payload).encode()
    return db_client.post("/api/v1/webhooks/shopify", content=body, headers=shopify_headers(body, topic, webhook_id, **kw))


def use_shopify(**changes):
    app.dependency_overrides[get_settings] = lambda: settings(shopify_webhook_secret=SHOPIFY_SECRET, **changes)


def test_the_shopify_signature_is_checked():
    body = b'{"id":1}'
    good = base64.b64encode(hmac.new(b"s", body, hashlib.sha256).digest()).decode()
    assert shopify_hooks.verify_hmac("s", body, good)
    assert not shopify_hooks.verify_hmac("s", body + b" ", good) and not shopify_hooks.verify_hmac("other", body, good)
    assert not shopify_hooks.verify_hmac("s", body, None) and not shopify_hooks.verify_hmac(None, body, good) and not shopify_hooks.verify_hmac("", body, good)


def test_a_bad_signature_changes_nothing(db_client, db_session):
    use_shopify()
    body = json.dumps(ORDER_PAYLOAD).encode()
    assert db_client.post("/api/v1/webhooks/shopify", content=body).status_code == 403
    assert post_shopify(db_client, ORDER_PAYLOAD, "orders/create", "w1", secret="wrong").status_code == 403
    use_shopify(shopify_shop_domain="my-own-shop.myshopify.com")
    assert post_shopify(db_client, ORDER_PAYLOAD, "orders/create", "w2").status_code == 403                    # a different shop
    app.dependency_overrides[get_settings] = lambda: settings()                                              # no secret configured
    assert post_shopify(db_client, ORDER_PAYLOAD, "orders/create", "w3").status_code == 403
    assert db_session.query(Order).count() == 0 and db_session.query(Customer).count() == 0


def test_a_new_shopify_order_creates_the_customer_order_consent_and_the_confirmed_status(db_client, db_session):
    use_shopify()
    always_open(db_session)
    make_template(db_session, "order_confirmed", channel="email", body="Hi {{first_name}}, order {{order_number}} confirmed.")
    response = post_shopify(db_client, ORDER_PAYLOAD, "orders/create", "w10")
    assert response.status_code == 200 and response.json()["recorded"] is True
    order = db_session.query(Order).one()
    assert (order.external_id, order.order_value, order.payment_type, order.city, order.products, order.item_count, order.source) == \
        ("SHOPIFY-450789469", Decimal("2500.00"), "cod", "Lahore", "Test shoes, Test bag", 3, "shopify")
    customer = db_session.query(Customer).one()
    assert (customer.phone_normalised, customer.email, customer.first_name) == ("+923001234567", "ali.test@testcustomer.test", "Test")
    assert consent.consent_state(db_session, customer.id, "email") == "opted_in" and consent.consent_state(db_session, customer.id, "whatsapp") == "none"
    assert order_status.latest_status(db_session, order.id).status == "confirmed"
    message = db_session.query(Message).one()
    assert message.channel == "email" and message.status == "sent" and "#1001" in message.rendered_text


def test_shopify_retries_and_repeats_do_not_double_anything(db_client, db_session):
    use_shopify()
    post_shopify(db_client, ORDER_PAYLOAD, "orders/create", "w20")
    assert post_shopify(db_client, ORDER_PAYLOAD, "orders/create", "w20").json() == {"ok": True, "duplicate": True}      # the same webhook id
    post_shopify(db_client, ORDER_PAYLOAD, "orders/create", "w21")                                                      # a new call, the same order
    assert db_session.query(Order).count() == 1 and db_session.query(Customer).count() == 1
    assert db_session.query(OrderStatusHistory).count() == 1


def test_a_customer_who_opted_out_is_not_opted_in_again_by_the_checkout_box(db_client, db_session):
    use_shopify()
    existing = make_customer(db_session, email="ali.test@testcustomer.test")
    consent.set_consent(db_session, existing.id, "email", False, "email_unsubscribe")
    post_shopify(db_client, ORDER_PAYLOAD, "orders/create", "w30")
    assert consent.consent_state(db_session, existing.id, "email") == "opted_out"
    assert db_session.query(Customer).count() == 1                                                                      # matched by phone, not duplicated


def test_shopify_fulfillments_move_the_order_along_with_courier_and_tracking(db_client, db_session):
    use_shopify()
    always_open(db_session)
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    make_template(db_session, "order_dispatched")
    make_template(db_session, "order_out_for_delivery")
    make_template(db_session, "order_delivered")
    post_shopify(db_client, {**ORDER_PAYLOAD, "customer": {"id": 1, "first_name": "Test", "phone": "0300 1234567"}}, "orders/create", "w40")
    order = db_session.query(Order).one()
    base = {"order_id": 450789469, "tracking_company": "TCS", "tracking_number": "TRK555"}
    created = post_shopify(db_client, {**base, "status": "success"}, "fulfillments/create", "w41").json()
    assert created["status"] == "dispatched" and "TRK555" in db_session.query(Message).filter_by(order_id=order.id, status="sent").all()[-1].rendered_text
    assert post_shopify(db_client, {**base, "shipment_status": "out_for_delivery"}, "fulfillments/update", "w42").json()["status"] == "out_for_delivery"
    assert post_shopify(db_client, {**base, "shipment_status": "delivered"}, "fulfillments/update", "w43").json()["status"] == "delivered"
    assert order_status.latest_status(db_session, order.id).status == "delivered"
    assert post_shopify(db_client, {**base, "shipment_status": "label_printed"}, "fulfillments/update", "w44").json()["ignored"].startswith("shipment_status")
    assert post_shopify(db_client, {**base, "order_id": 999}, "fulfillments/create", "w45").json() == {"ok": True, "ignored": "unknown order"}


def test_other_shopify_topics_are_accepted_and_ignored(db_client):
    use_shopify()
    assert post_shopify(db_client, {"id": 1}, "customers/update", "w50").json() == {"ok": True, "ignored": "customers/update"}
    assert db_client.post("/api/v1/webhooks/shopify", content=b"[]", headers=shopify_headers(b"[]", "orders/create", "w51")).status_code == 400


# --- courier status files ---------------------------------------------------------------------------------------------------------------


def import_shipments_csv(db_client, rows):
    header = "order_id,courier_name,city,booked_date,status,delivered_or_returned_date,tracking_number,data_source\n"
    return db_client.post("/api/v1/shipments/import", files={"file": ("s.csv", io.BytesIO((header + rows).encode()), "text/csv")})


def test_a_fresh_courier_status_messages_the_customer_and_an_old_one_does_not(db_client, db_session, monkeypatch):
    app.dependency_overrides[get_settings] = lambda: settings()
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    fresh, stale = make_order(db_session, customer, external_id="TEST-FRESH"), make_order(db_session, customer, external_id="TEST-STALE")
    make_template(db_session, "order_delivered")
    make_template(db_session, "order_in_transit")
    today, old = date.today(), date.today() - timedelta(days=60)
    rows = (
        f"TEST-FRESH,TCS,Lahore,{today - timedelta(days=2)},delivered,{today},TRK-77,\n"
        f"TEST-STALE,TCS,Lahore,{old},delivered,{old + timedelta(days=3)},TRK-78,\n"
    )
    assert import_shipments_csv(db_client, rows).status_code == 201
    assert order_status.latest_status(db_session, fresh.id).status == "delivered"
    assert order_status.latest_status(db_session, stale.id) is None                                         # too old to even record
    assert db_session.query(Message).filter_by(order_id=fresh.id).count() == 1 and db_session.query(Message).filter_by(order_id=stale.id).count() == 0
    assert "TRK-77" in {s.tracking_number for s in db_session.query(Shipment)}


def test_importing_again_without_the_tracking_column_keeps_the_saved_number(db_client, db_session):
    app.dependency_overrides[get_settings] = lambda: settings()
    customer = make_customer(db_session)
    make_order(db_session, customer, external_id="TEST-KEEP")
    day = date.today() - timedelta(days=2)
    import_shipments_csv(db_client, f"TEST-KEEP,TCS,Lahore,{day},in_transit,,TRK-1,\n")
    db_client.post("/api/v1/shipments/import", files={"file": ("s.csv", io.BytesIO(f"order_id,courier_name,city,booked_date,status\nTEST-KEEP,TCS,Lahore,{day},in_transit\n".encode()), "text/csv")})
    assert db_session.query(Shipment).one().tracking_number == "TRK-1"


def test_demo_shipments_never_message_anyone(db_client, db_session):
    app.dependency_overrides[get_settings] = lambda: settings()
    customer = make_customer(db_session)
    opt_in(db_session, customer)
    order = make_order(db_session, customer, external_id="TEST-DEMO")
    make_template(db_session, "order_delivered")
    day = date.today()
    import_shipments_csv(db_client, f"TEST-DEMO,TCS,Lahore,{day - timedelta(days=2)},delivered,{day},,demo (synthetic)\n")
    assert order_status.latest_status(db_session, order.id) is None and db_session.query(Message).count() == 0


def test_a_messaging_problem_never_breaks_a_good_import(db_client, db_session, monkeypatch):
    app.dependency_overrides[get_settings] = lambda: settings()
    make_order(db_session, make_customer(db_session), external_id="TEST-BOOM")

    def boom(*args, **kwargs):
        raise RuntimeError("messaging is down")

    monkeypatch.setattr(order_status, "record_from_shipment", boom)
    response = import_shipments_csv(db_client, f"TEST-BOOM,TCS,Lahore,{date.today() - timedelta(days=1)},delivered,{date.today()},,\n")
    assert response.status_code == 201 and response.json()["created"] == 1


# --- adding an order by hand ----------------------------------------------------------------------------------------------------------------


def test_adding_an_order_with_the_whatsapp_box_ticked_records_consent_and_confirms(db_client, db_session):
    app.dependency_overrides[get_settings] = lambda: settings()
    make_template(db_session, "order_confirmed", body="Confirmed {{first_name}} {{order_number}}")
    body = {"customerName": "Test Sara", "phone": "0300 5551234", "city": "Lahore", "products": ["Test shoes"], "amount": "2500", "paymentType": "cod", "channel": "whatsapp", "whatsappOk": True}
    assert db_client.post("/api/v1/orders", json=body).status_code == 201
    customer = db_session.query(Customer).filter_by(phone_normalised="+923005551234").one()
    assert consent.consent_state(db_session, customer.id, "whatsapp") == "opted_in"
    assert db_session.query(consent.CustomerConsent).filter_by(customer_id=customer.id).one().source == "add_order"
    message = db_session.query(Message).filter_by(customer_id=customer.id).one()
    assert message.status in ("sent", "queued") and message.rendered_text.startswith("Confirmed Test Sara")


def test_adding_an_order_without_the_box_ticked_sends_nothing(db_client, db_session):
    app.dependency_overrides[get_settings] = lambda: settings()
    make_template(db_session, "order_confirmed")
    body = {"customerName": "Test Sara", "phone": "0300 5551234", "city": "Lahore", "products": ["Test shoes"], "amount": "2500", "paymentType": "cod", "channel": "whatsapp"}
    assert db_client.post("/api/v1/orders", json=body).status_code == 201
    customer = db_session.query(Customer).filter_by(phone_normalised="+923005551234").one()
    assert consent.consent_state(db_session, customer.id, "whatsapp") == "none"
    assert db_session.query(Message).filter_by(customer_id=customer.id).one().error == "no_consent"
