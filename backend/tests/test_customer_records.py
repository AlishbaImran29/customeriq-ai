"""Customer records: erasing a customer, timeline, export. Everything is made up (marked TEST)."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import Customer, CustomerAudit, CustomerConsent, IncomingMessage, Message, Order
from app.services import customer_records as records
from app.services.messaging import consent

NOW = datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc)
_n = [0]


def person(db, *, email=None, phone=None, name="Test Ali", notes=None, tags=None, language=None):
    _n[0] += 1
    c = Customer(external_id=f"TEST-CR{_n[0]}", email=email, first_name=name, phone=phone, phone_normalised=phone, preferred_language=language, notes=notes, tags=tags or [])
    db.add(c)
    db.flush()
    return c


def order(db, c, *, note=None):
    _n[0] += 1
    o = Order(external_id=f"TEST-CRORD-{_n[0]}", customer_id=c.id, order_date=date(2026, 3, 1), order_value=Decimal(1000), products="Test shoes", note=note, source="manual")
    db.add(o)
    db.flush()
    return o


def settings():
    return Settings(_env_file=None)


def test_anonymise_removes_the_person_but_keeps_the_orders(db_session):
    c = person(db_session, email="who@test.example", phone="+923009998877", name="Test Sara", notes="secret", tags=["vip"])
    o = order(db_session, c, note="deliver to house 5")
    consent.set_consent(db_session, c.id, "whatsapp", True, "manual")
    db_session.add(Message(customer_id=c.id, channel="whatsapp", category="utility", rendered_text="Hi Test Sara", status="sent", idempotency_key="test-cr-msg-1"))
    db_session.add(IncomingMessage(customer_id=c.id, channel="whatsapp", from_address="+923009998877", provider_message_id="wamid.CR1", message_type="text", body="hello", received_at=NOW))
    db_session.flush()
    records.anonymise(db_session, settings(), c.id)
    db_session.expire_all()
    assert (c.first_name, c.email, c.phone, c.phone_normalised, c.notes, c.tags, c.status) == (None, None, None, None, None, [], "anonymised")
    assert c.external_id == f"ANON-{c.id}" and c.anonymised_at is not None
    assert db_session.get(Order, o.id).note is None and db_session.get(Order, o.id).customer_id == c.id      # the sale stays, anonymously
    assert db_session.query(Message).filter(Message.customer_id == c.id).count() == 0
    assert db_session.query(IncomingMessage).filter(IncomingMessage.customer_id == c.id).count() == 0
    assert db_session.query(CustomerConsent).filter(CustomerConsent.customer_id == c.id).count() == 0
    audit = db_session.query(CustomerAudit).one()
    assert audit.action == "anonymise" and audit.detail["messages"] == 1
    assert "Sara" not in str(audit.detail) and "secret" not in str(audit.detail)
    with pytest.raises(ApiError):
        records.anonymise(db_session, settings(), c.id)                      # twice is refused


def test_delete_removes_the_customer_and_their_orders(db_session):
    c = person(db_session)
    order(db_session, c)
    records.delete_customer(db_session, settings(), c.id)
    db_session.flush()
    assert db_session.query(Customer).filter(Customer.id == c.id).count() == 0
    assert db_session.query(Order).filter(Order.customer_id == c.id).count() == 0
    assert db_session.query(CustomerAudit).one().detail["orders"] == 1


def test_timeline_lists_orders_messages_replies_and_consent_newest_first(db_session):
    c = person(db_session, phone="+923001112233")
    order(db_session, c)
    consent.set_consent(db_session, c.id, "whatsapp", True, "manual")
    db_session.add(Message(customer_id=c.id, channel="whatsapp", category="utility", rendered_text="Hello there", status="sent", sent_at=NOW, idempotency_key="test-cr-msg-2"))
    db_session.add(IncomingMessage(customer_id=c.id, channel="whatsapp", from_address="+923001112233", provider_message_id="wamid.CR2", message_type="text", body="thanks", received_at=NOW))
    db_session.flush()
    events = records.timeline(db_session, c)
    assert {e.kind for e in events} == {"order", "message", "reply", "consent"}
    assert [e.at for e in events] == sorted((e.at for e in events), reverse=True)


def test_export_is_safe_for_spreadsheets_and_leaves_erased_customers_out(db_session):
    person(db_session, name="=HYPERLINK(1)", email="e@test.example")
    gone = person(db_session, name="Test Gone")
    records.anonymise(db_session, settings(), gone.id)
    text = records.export_csv(db_session)
    assert "'=HYPERLINK(1)" in text and "Test Gone" not in text and f"ANON-{gone.id}" not in text


def test_api_profile_erase_and_audit(db_client, db_session):
    a = person(db_session, email="dup@test.example", name="Test A")
    db_session.commit()
    original_id = a.external_id
    r = db_client.patch("/api/v1/customer-records/profile", params={"id": original_id}, json={"notes": "n", "tags": ["x", "X", " y "], "acquisitionSource": "instagram"})
    assert r.status_code == 200 and r.json()["tags"] == ["x", "y"] and r.json()["acquisitionSource"] == "instagram"
    assert db_client.post("/api/v1/customer-records/delete", json={"customerId": a.external_id}).status_code == 422
    assert db_client.post("/api/v1/customer-records/anonymise", json={"customerId": a.external_id, "confirm": True}).status_code == 200
    assert db_client.get("/api/v1/customer-records/profile", params={"id": original_id}).status_code == 404            # its id changed
    actions = [x["action"] for x in db_client.get("/api/v1/customer-records/audit").json()]
    assert actions == ["anonymise", "edit"]
    assert db_client.get("/api/v1/customer-records/export.csv").headers["content-type"].startswith("text/csv")
