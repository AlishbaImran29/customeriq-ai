"""Customer records: duplicates, safe merge, erasing a customer, timeline, export. Everything is made up (marked TEST)."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import ConsentEvent, Customer, CustomerAudit, CustomerConsent, IncomingMessage, Message, Order, Shipment
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


def test_customers_sharing_an_email_are_listed_as_duplicates(db_session):
    a, b = person(db_session, email="Same@Test.Example"), person(db_session, email="same@test.example")
    person(db_session, email="other@test.example")
    groups = records.find_duplicates(db_session)
    assert len(groups) == 1 and {c.id for c in groups[0].customers} == {a.id, b.id}


def test_merge_moves_everything_and_fills_empty_fields(db_session):
    keep = person(db_session, email=None, name="Test Ali", tags=["vip"], notes="likes red")
    other = person(db_session, email="x@test.example", phone="+923001234567", tags=["Eid", "VIP"], notes="calls at night", language="ur")
    order(db_session, keep)
    moved = order(db_session, other)
    db_session.add(Shipment(external_id="TEST-SHIP-CR1", order_id=moved.id, customer_id=other.id, courier="TCS", booked_date=date(2026, 3, 1), status="delivered"))
    db_session.flush()
    records.merge(db_session, keep.id, other.id)
    db_session.flush()
    db_session.expire_all()
    assert db_session.get(Customer, other.id) is None
    assert db_session.query(Order).filter(Order.customer_id == keep.id).count() == 2
    assert db_session.query(Shipment).filter(Shipment.customer_id == keep.id).count() == 1
    assert (keep.email, keep.phone_normalised, keep.preferred_language) == ("x@test.example", "+923001234567", "ur")
    assert keep.tags == ["vip", "Eid"]                                       # joined, not repeated (VIP = vip)
    assert keep.notes == "likes red\n---\ncalls at night"
    audit = db_session.query(CustomerAudit).one()
    assert audit.action == "merge" and audit.detail["orders"] == 1 and "x@test.example" not in str(audit.detail)


def test_merge_keeps_an_opt_out_from_either_side(db_session):
    keep, other = person(db_session, email="a@test.example"), person(db_session, email="b@test.example")
    consent.set_consent(db_session, keep.id, "whatsapp", True, "manual")
    consent.set_consent(db_session, other.id, "whatsapp", False, "whatsapp_stop")
    consent.set_consent(db_session, other.id, "email", True, "manual")
    records.merge(db_session, keep.id, other.id)
    db_session.expire_all()
    rows = {c.channel: c.opted_in for c in db_session.query(CustomerConsent).filter(CustomerConsent.customer_id == keep.id)}
    assert rows == {"whatsapp": False, "email": True}
    assert db_session.query(ConsentEvent).filter(ConsentEvent.customer_id == keep.id).count() == 3      # the history came along


def test_merge_refuses_nonsense(db_session):
    a = person(db_session)
    with pytest.raises(ApiError):
        records.merge(db_session, a.id, a.id)
    with pytest.raises(ApiError):
        records.merge(db_session, a.id, 999999)


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


def test_api_profile_merge_erase_and_audit(db_client, db_session):
    a, b = person(db_session, email="dup@test.example", name="Test A"), person(db_session, email="dup@test.example", name="Test B")
    db_session.commit()
    original_id = a.external_id
    r = db_client.patch("/api/v1/customer-records/profile", params={"id": original_id}, json={"notes": "n", "tags": ["x", "X", " y "], "acquisitionSource": "instagram"})
    assert r.status_code == 200 and r.json()["tags"] == ["x", "y"] and r.json()["acquisitionSource"] == "instagram"
    groups = db_client.get("/api/v1/customer-records/duplicates").json()
    assert len(groups) == 1 and len(groups[0]["customers"]) == 2
    assert db_client.post("/api/v1/customer-records/merge", json={"keepId": a.id, "mergeId": b.id}).status_code == 422       # needs confirm
    ok = db_client.post("/api/v1/customer-records/merge", json={"keepId": a.id, "mergeId": b.id, "confirm": True})
    assert ok.status_code == 200 and ok.json()["id"] == a.id
    assert db_client.get("/api/v1/customer-records/duplicates").json() == []
    assert db_client.post("/api/v1/customer-records/delete", json={"customerId": a.external_id}).status_code == 422
    assert db_client.post("/api/v1/customer-records/anonymise", json={"customerId": a.external_id, "confirm": True}).status_code == 200
    assert db_client.get("/api/v1/customer-records/profile", params={"id": original_id}).status_code == 404            # its id changed
    actions = [x["action"] for x in db_client.get("/api/v1/customer-records/audit").json()]
    assert actions == ["anonymise", "merge", "edit"]
    assert db_client.get("/api/v1/customer-records/export.csv").headers["content-type"].startswith("text/csv")
