"""Support inbox: intent guess, replies drafted only from records (never invented), escalation, typed replies, notes, response time.
Customers and messages are made up (marked TEST); nothing is really sent."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import IncomingMessage, Message, Shipment
from app.models.inbox import FaqEntry
from app.models.inventory import StockItem
from app.services import inbox
from tests.test_order_status import NOON, make_customer, make_order, opt_in, record

NOW = datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc)


def settings() -> Settings:
    return Settings(_env_file=None, messaging_dry_run=True)


def wrote(db, customer, text, when=NOW):
    n = db.query(IncomingMessage).count()
    m = IncomingMessage(customer_id=customer.id, channel="whatsapp", from_address=customer.phone, provider_message_id=f"wamid.IN{n}-{when.timestamp()}", message_type="text", body=text, received_at=when)
    db.add(m)
    db.flush()
    return m


@pytest.mark.parametrize("text,intent", [
    ("Where is my order?", "order_status"), ("mera parcel kahan hai", "order_status"), ("tracking number do", "order_status"),
    ("I want a refund", "refund"), ("paisa wapas chahiye", "refund"), ("the shoes are damaged", "complaint"), ("ye kharab hai", "complaint"),
    ("I want to return this", "return"), ("size badalna hai", "return"), ("I will go to consumer court", "dispute"),
    ("What is the price of the red bag?", "product_question"), ("kitne ka hai", "product_question"), ("hello", "other"), (None, "other"),
])
def test_the_intent_guess(text, intent):
    assert inbox.classify(text) == intent


def test_a_refund_request_is_a_refund_even_if_it_also_asks_for_the_order(db_session):
    assert inbox.classify("where is my order, I want my money back") == "refund"


def test_order_status_is_answered_from_the_customers_own_order_only(db_session):
    mine = make_customer(db_session, name="Test Sana")
    order = make_order(db_session, mine, products="Test shoes")
    record(db_session, order, "dispatched", courier="TCS", tracking="CN123", notify=False)
    s = inbox.suggest(db_session, mine, "Where is my order?")
    assert not s.escalate and "dispatched" in s.draft and "TCS" in s.draft and "CN123" in s.draft and "Test Sana".split()[0] in s.draft
    assert s.sources and s.sources[0].startswith("order ")


def test_nothing_is_invented_when_the_records_are_empty(db_session):
    stranger = make_customer(db_session, phone="+923009998877")
    s = inbox.suggest(db_session, stranger, "Where is my order?")
    assert s.escalate and s.draft is None and "records" in s.reason
    only_confirmed = make_customer(db_session, phone="+923008887766")
    make_order(db_session, only_confirmed)                                                    # an order with no status yet
    assert inbox.suggest(db_session, only_confirmed, "order status?").draft is None


def test_product_questions_use_the_stock_list_and_say_when_it_is_out(db_session):
    db_session.add(StockItem(sku="TST-B", name="Red bag", selling_price=1999, stock=3))
    db_session.add(StockItem(sku="TST-C", name="Blue cap", selling_price=499, stock=0))
    c = make_customer(db_session)
    both = inbox.suggest(db_session, c, "price of the red bag and the blue cap?")
    assert "Red bag: Rs 1,999, in stock." in both.draft and "Blue cap: Rs 499, out of stock right now." in both.draft
    assert inbox.suggest(db_session, c, "do you have a green hat, what is the price?").escalate is True   # not in the list: no guess


def test_the_sellers_own_faq_can_answer_and_complaints_never_get_a_draft(db_session):
    db_session.add(FaqEntry(title="Delivery time", keywords="how long, kitne din", answer="delivery takes 3 to 5 working days."))
    c = make_customer(db_session)
    assert "3 to 5 working days" in inbox.suggest(db_session, c, "how long does delivery take?").draft
    for text in ("my order arrived damaged", "I want a refund", "please exchange it", "I will call the police"):
        s = inbox.suggest(db_session, c, text)
        assert s.escalate and s.draft is None


def test_no_number_in_a_draft_comes_from_anywhere_but_the_records(db_session):
    import re

    db_session.add(StockItem(sku="TST-D", name="Test mug", selling_price=750, stock=5))
    c = make_customer(db_session)
    draft = inbox.suggest(db_session, c, "price of the test mug?").draft
    assert set(re.findall(r"\d+(?:,\d{3})*", draft)) <= {"750"}


def test_a_typed_reply_goes_through_the_normal_checks(db_session):
    c = make_customer(db_session)
    opt_in(db_session, c)
    message = inbox.reply(db_session, settings(), c, "Your parcel leaves today.", now=NOW)
    assert message.status in ("sent", "queued") and message.rendered_text == "Your parcel leaves today."
    with pytest.raises(ApiError):
        inbox.reply(db_session, settings(), c, "Hello {{first_name}}", now=NOW)
    with pytest.raises(ApiError):
        inbox.reply(db_session, settings(), c, "  ", now=NOW)
    no_consent = make_customer(db_session, phone="+923007776655")
    assert inbox.reply(db_session, settings(), no_consent, "Hi", now=NOW).status == "skipped"       # consent still applies


def test_the_24_hour_rule_is_enforced_when_not_in_dry_run(db_session):
    c = make_customer(db_session)
    opt_in(db_session, c)
    live = Settings(_env_file=None, messaging_dry_run=False, whatsapp_access_token="t", whatsapp_phone_number_id="1")
    from app.services.messaging.settings_store import get_row

    get_row(db_session).dry_run = False
    with pytest.raises(ApiError) as caught:
        inbox.reply(db_session, live, c, "Hi", now=NOW)
    assert caught.value.code == "session_closed"


def test_response_time_counts_only_typed_replies_and_needs_enough_questions(db_session):
    c = make_customer(db_session)
    opt_in(db_session, c)
    for i in range(inbox.data_rules.MIN_GROUP_COUNT):
        asked = NOW + timedelta(hours=i)
        wrote(db_session, c, "question", asked)
        inbox.reply(db_session, settings(), c, f"answer {i}", now=asked + timedelta(minutes=10))
    average, measured = inbox.response_minutes(db_session, NOW + timedelta(days=2))
    assert measured == inbox.data_rules.MIN_GROUP_COUNT and average == pytest.approx(10.0)
    assert inbox.response_minutes(db_session, NOW + timedelta(days=60)) == (None, 0)         # outside the window


def test_api_inbox_flow(db_client, db_session):
    c = make_customer(db_session, name="Test Hina")
    opt_in(db_session, c)
    order = make_order(db_session, c)
    record(db_session, order, "out_for_delivery", notify=False)
    wrote(db_session, c, "Where is my order?", datetime.now(timezone.utc) - timedelta(minutes=5))
    db_session.commit()
    listing = db_client.get("/api/v1/inbox").json()
    assert listing[0]["customerId"] == c.id and listing[0]["unread"] == 1 and listing[0]["intent"] == "order_status"
    thread = db_client.get(f"/api/v1/inbox/{c.id}").json()
    assert thread["suggestion"]["draft"].startswith("Hello Test") and "Not AI" in thread["suggestion"]["label"] or "not AI" in thread["suggestion"]["label"]
    assert db_client.get("/api/v1/inbox").json()[0]["unread"] == 0                                       # opening it marks it read
    sent = db_client.post(f"/api/v1/inbox/{c.id}/reply", json={"text": "It arrives today."})
    assert sent.status_code == 201 and sent.json()["kind"] == "typed"
    assert db_client.get(f"/api/v1/inbox/{c.id}").json()["suggestion"] is None                           # already answered
    assert db_client.post(f"/api/v1/inbox/{c.id}/notes", json={"body": "Called courier"}).status_code == 201
    assert db_client.patch(f"/api/v1/inbox/{c.id}", json={"assignedTo": "staff@test.example", "status": "closed"}).json() == {"status": "closed", "assignedTo": "staff@test.example"}
    assert db_client.get("/api/v1/inbox?state=open").json() == []
    assert db_client.get(f"/api/v1/inbox/{c.id}").json()["notes"][0]["body"] == "Called courier"
    assert db_client.get("/api/v1/inbox/999999").status_code == 404
    faq = db_client.post("/api/v1/inbox/faq/list", json={"title": "Returns", "keywords": "return window", "answer": "7 days."})
    assert faq.status_code == 201 and db_client.get("/api/v1/inbox/faq/list").json()[0]["title"] == "Returns"
    assert db_client.get("/api/v1/inbox/metrics").json()["averageResponseMinutes"] is None
    templates = db_client.get("/api/v1/messaging/templates").json()
    assert all(t["event"] != "manual_reply" for t in templates)                                           # typed replies are not shown as templates
