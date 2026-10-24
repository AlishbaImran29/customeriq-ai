"""COD auto-confirmation: ask, read the answer (YES / NO / buttons), release stock on NO, time out to "needs a call",
and raise the Order Risk level. Customers and messages are made up (marked TEST); nothing is really sent."""

from datetime import datetime, timedelta, timezone

from app.models import Customer, Message, Order
from app.models.cod_confirmation import CodConfirmation
from app.models.inventory import StockItem
from app.services import inventory
from app.services.messaging import cod_confirm, webhook
from tests.test_messaging_media import text_payload
from tests.test_order_status import NOON, make_customer, make_order, make_template, opt_in, settings

PHONE_DIGITS = "923001234567"


def ready(db, *, approved=True, consent=True, payment="cod", products="Test shoes", phone="+923001234567"):
    customer = make_customer(db, phone=phone)
    if consent:
        opt_in(db, customer)
    make_template(db, "cod_confirmation", approved=approved, body="Hi {{first_name}}, confirm {{order_number}} for {{amount}}? Reply YES or NO.")
    return customer, make_order(db, customer, payment=payment, products=products)


def test_a_cod_order_is_asked_once_and_waits_for_an_answer(db_session):
    customer, order = ready(db_session)
    confirmation = cod_confirm.ask(db_session, settings(), order, NOON)
    assert confirmation.state == "awaiting" and confirmation.deadline_at == NOON + timedelta(hours=cod_confirm.COD_CONFIRM_HOURS)
    assert db_session.query(Message).filter(Message.order_id == order.id).count() == 1
    assert cod_confirm.ask(db_session, settings(), order, NOON) is None             # asking again does nothing


def test_nobody_is_asked_without_consent(db_session):
    _, order = ready(db_session, consent=False)
    assert cod_confirm.ask(db_session, settings(), order, NOON) is None
    assert db_session.query(CodConfirmation).count() == 0


def test_nobody_is_asked_until_the_seller_approves_the_template(db_session):
    _, order = ready(db_session, approved=False)
    assert cod_confirm.ask(db_session, settings(), order, NOON) is None
    assert db_session.query(Message).count() == 0


def test_a_prepaid_order_is_never_asked(db_session):
    _, order = ready(db_session, payment="prepaid")
    assert cod_confirm.ask(db_session, settings(), order, NOON) is None


def test_yes_confirms_and_a_second_answer_is_not_a_second_confirmation(db_session):
    customer, order = ready(db_session)
    cod_confirm.ask(db_session, settings(), order, NOON)
    webhook.process_whatsapp_payload(db_session, text_payload("wamid.COD1", PHONE_DIGITS, "YES"), NOON)
    row = cod_confirm.get(db_session, order.id)
    assert (row.state, row.resolved_by, row.reply_text) == ("confirmed", "customer", "YES")


def test_no_cancels_and_gives_the_reserved_stock_back(db_session):
    customer, order = ready(db_session, products="Test lip balm x2")
    item = StockItem(sku="TST-C", name="Test lip balm", stock=10)
    db_session.add(item)
    db_session.flush()
    inventory.reserve_order(db_session, order)
    assert item.reserved == 2
    cod_confirm.ask(db_session, settings(), order, NOON)
    webhook.process_whatsapp_payload(db_session, text_payload("wamid.COD2", PHONE_DIGITS, "nahi"), NOON)
    assert cod_confirm.get(db_session, order.id).state == "cancelled"
    assert (item.stock, item.reserved) == (10, 0)


def test_a_cancel_button_cancels_the_order_but_does_not_switch_messages_off(db_session):
    from app.services.messaging import consent

    customer, order = ready(db_session)
    cod_confirm.ask(db_session, settings(), order, NOON)
    payload = {"entry": [{"changes": [{"value": {"messages": [{"id": "wamid.BTN1", "from": PHONE_DIGITS, "type": "button", "timestamp": "1773000100", "button": {"text": "Cancel", "payload": "Cancel"}}]}}]}]}
    webhook.process_whatsapp_payload(db_session, payload, NOON)
    assert cod_confirm.get(db_session, order.id).state == "cancelled"
    assert consent.consent_state(db_session, customer.id, "whatsapp") == "opted_in"


def test_an_interactive_button_reply_is_read_too(db_session):
    customer, order = ready(db_session)
    cod_confirm.ask(db_session, settings(), order, NOON)
    payload = {"entry": [{"changes": [{"value": {"messages": [{"id": "wamid.BTN2", "from": PHONE_DIGITS, "type": "interactive", "timestamp": "1773000100", "interactive": {"button_reply": {"id": "confirm", "title": "Confirm"}}}]}}]}]}
    webhook.process_whatsapp_payload(db_session, payload, NOON)
    assert cod_confirm.get(db_session, order.id).state == "confirmed"


def test_an_answer_with_no_open_question_is_not_a_cod_answer(db_session):
    customer, order = ready(db_session)
    assert cod_confirm.apply_answer(db_session, customer.id, "yes", "YES", NOON) is None
    cod_confirm.ask(db_session, settings(), order, NOON)
    assert cod_confirm.apply_answer(db_session, customer.id, "yes", "YES", NOON + timedelta(days=5)) is None     # too late to be an answer


def test_no_answer_by_the_deadline_needs_a_call(db_session):
    customer, order = ready(db_session)
    cod_confirm.ask(db_session, settings(), order, NOON)
    assert cod_confirm.mark_overdue(db_session, NOON + timedelta(hours=cod_confirm.COD_CONFIRM_HOURS - 1)) == {"needs_call": 0}
    later = NOON + timedelta(hours=cod_confirm.COD_CONFIRM_HOURS + 1)
    assert cod_confirm.mark_overdue(db_session, later) == {"needs_call": 1}
    assert cod_confirm.mark_overdue(db_session, later) == {"needs_call": 0}                                      # only once
    assert cod_confirm.get(db_session, order.id).state == "needs_call"
    webhook.process_whatsapp_payload(db_session, text_payload("wamid.COD3", PHONE_DIGITS, "yes"), later)         # a late YES still counts
    assert cod_confirm.get(db_session, order.id).state == "confirmed"


def test_the_seller_can_record_a_phone_call(db_session):
    customer, order = ready(db_session)
    cod_confirm.ask(db_session, settings(), order, NOON)
    cod_confirm.mark_overdue(db_session, NOON + timedelta(days=1))
    row = cod_confirm.resolve(db_session, order.id, "cancelled", NOON + timedelta(days=1))
    assert (row.state, row.resolved_by) == ("cancelled", "seller")


def test_api_lists_and_resolves(db_client, db_session):
    customer, order = ready(db_session)
    db_session.add(CodConfirmation(order_id=order.id, state="needs_call", asked_at=NOON, deadline_at=NOON))
    db_session.commit()
    rows = db_client.get("/api/v1/messaging/cod").json()
    assert [r["state"] for r in rows] == ["needs_call"] and rows[0]["orderId"] == order.id
    r = db_client.post(f"/api/v1/messaging/cod/{order.id}/resolve", json={"result": "confirmed"})
    assert r.status_code == 200 and r.json()["state"] == "confirmed" and r.json()["resolvedBy"] == "seller"
    assert db_client.post(f"/api/v1/messaging/cod/{order.id}/resolve", json={"result": "maybe"}).status_code == 422
    assert db_client.post("/api/v1/messaging/cod/999999/resolve", json={"result": "confirmed"}).status_code == 404


def test_no_reply_raises_the_order_risk_level_one_step_and_says_why(db_client, db_session, monkeypatch):
    from app.services import order_risk_service
    from tests.test_order_risk_model import make_orders

    order_risk_service.clear_cache()
    orders = make_orders(signal=True)
    monkeypatch.setattr(order_risk_service, "load_order_inputs", lambda db: orders)
    before = db_client.get("/api/v1/order-risk?limit=1000").json()
    low = next(o for o in before["orders"] if o["level"] == "Low")
    customer = make_customer(db_session)
    order = make_order(db_session, customer, external_id=low["orderId"])
    db_session.add(CodConfirmation(order_id=order.id, state="needs_call", asked_at=NOON, deadline_at=NOON))
    db_session.commit()
    after = db_client.get("/api/v1/order-risk?limit=1000").json()
    row = next(o for o in after["orders"] if o["orderId"] == low["orderId"])
    assert row["level"] == "Medium" and any("No reply" in r["text"] for r in row["reasons"])
    assert after["levelCounts"]["Low"] == before["levelCounts"]["Low"] - 1 and after["levelCounts"]["Medium"] == before["levelCounts"]["Medium"] + 1
    order_risk_service.clear_cache()
