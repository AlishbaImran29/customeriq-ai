"""WhatsApp chat import API: reading a chat, saving only what was accepted, and deleting it again.

Every chat used here is made up (tests/fixtures/whatsapp/README.md).
"""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text

from app.api.v1 import whatsapp_import
from app.main import app
from app.models import Customer, Order
from tests.conftest import requires_database
from tests.test_whatsapp_chat import FIXTURES

BASE = "/api/v1/whatsapp-import"


@pytest.fixture
def client():
    return TestClient(app)


def upload(client, name="TESTDATA_android_12h.txt", filename="WhatsApp Chat with Ayesha.txt", **form):
    data = (FIXTURES / name).read_bytes() if isinstance(name, str) else name
    return client.post(f"{BASE}/parse", files={"file": (filename, data, "text/plain")}, data=form)


def accepted(candidate, **changes):
    """What the review screen sends for an accepted candidate (products are typed by the seller)."""
    row = {
        "customerName": candidate["customerName"] or "Customer", "phone": candidate["phone"], "city": candidate["city"] or "Lahore",
        "products": ["Lawn suit"], "amount": candidate["amount"], "paymentType": candidate["paymentType"] or "cod",
        "orderDate": candidate["orderDate"], "messageTime": candidate["orderTime"],
    }
    row.update(changes)
    return row


# --- reading a chat (nothing is saved) -----------------------------------------------------------------

def test_a_chat_is_read_and_orders_are_suggested(client):
    body = upload(client).json()
    assert body["dateOrder"] == "dmy" and body["dateOrderAmbiguous"] is False
    assert body["customerNameHint"] == "Ayesha" and body["messageCount"] == 7
    assert {s["name"] for s in body["senders"]} == {"Ayesha", "Sana Boutique", "Bilal"}
    first = body["candidates"][0]
    assert (first["customerName"], first["phone"], first["city"], first["amount"]) == ("Ayesha", "+923001234567", "Lahore", 4500.0)
    assert first["confidence"] == "high" and first["confidenceLabel"] == "Amount and phone found"
    assert first["paymentType"] == "cod" and first["orderDate"] == "2026-10-18"
    assert any("House 12" in m["text"] for m in first["messages"])           # the original messages, for review


def test_choosing_who_the_seller_is_removes_the_sellers_own_words(client):
    month_first = "TESTDATA_month_first.txt"
    assert len(upload(client, month_first).json()["candidates"]) == 2
    chosen = upload(client, month_first, me="Shop").json()
    assert chosen["me"] == "Shop" and [c["customerName"] for c in chosen["candidates"]] == ["Omar"]
    assert upload(client, month_first, me="Nobody").json()["me"] is None          # a name not in the chat is ignored


def test_an_ambiguous_date_is_reported_and_the_choice_is_applied(client):
    body = upload(client, "TESTDATA_ambiguous.txt").json()
    assert body["dateOrderAmbiguous"] is True and body["candidates"][0]["orderDate"] == "2026-03-02"
    chosen = upload(client, "TESTDATA_ambiguous.txt", dateOrder="mdy").json()
    assert chosen["dateOrderAmbiguous"] is False and chosen["candidates"][0]["orderDate"] == "2026-02-03"


def test_wrong_files_are_refused_with_a_plain_message(client):
    zipped = upload(client, b"PK\x03\x04", "WhatsApp Chat with Ali.zip")
    assert zipped.status_code == 415 and "Unzip" in zipped.json()["error"]["message"]
    assert upload(client, b"%PDF", "chat.pdf").status_code == 415
    assert upload(client, b"   \n", "chat.txt").status_code == 400
    # A text file that is not a chat is not an error: it simply has no orders.
    none = upload(client, b"hello there\nnothing here", "notes.txt").json()
    assert none["messageCount"] == 0 and none["candidates"] == []


def test_a_chat_over_the_size_limit_is_refused(client, monkeypatch):
    monkeypatch.setattr(whatsapp_import, "MAX_CHAT_BYTES", 50)
    response = upload(client, b"x" * 200, "big.txt")
    assert response.status_code == 413 and "Export fewer months" in response.json()["error"]["message"]


def test_reading_a_chat_logs_none_of_it(client, caplog):
    with caplog.at_level(logging.DEBUG):
        upload(client)
    for record in caplog.records:
        assert not any(word in record.getMessage() for word in ("House 12", "lawn suits", "0300-1234567", "Ayesha"))


@requires_database
def test_reading_a_chat_saves_nothing_anywhere(db_client, db_session):
    before = db_session.scalar(select(func.count()).select_from(Order)), db_session.scalar(select(func.count()).select_from(Customer))
    upload(db_client)
    assert (db_session.scalar(select(func.count()).select_from(Order)), db_session.scalar(select(func.count()).select_from(Customer))) == before


# --- saving what was accepted ----------------------------------------------------------------------------

@requires_database
def test_accepted_orders_are_saved_without_any_chat_text(db_client, db_session):
    candidates = upload(db_client, "TESTDATA_android_24h.txt", me="Shop").json()["candidates"]
    response = db_client.post(f"{BASE}/save", json={"orders": [accepted(c) for c in candidates]})
    assert response.status_code == 201, response.text
    assert response.json() == {"saved": 2, "alreadyImported": 0, "newCustomers": 2}

    orders = {o.customer.phone_normalised: o for o in db_session.scalars(select(Order))}
    zara = orders["+923219876543"]
    assert (zara.source, zara.sales_channel, zara.channel, zara.payment_type) == ("whatsapp_chat", "whatsapp", "Whatsapp", "prepaid")
    assert (zara.city, zara.products, zara.note, str(zara.order_value)) == ("Karachi", "Lawn suit", None, "1800.00")
    assert zara.external_id.startswith("WA-") and zara.customer.first_name == "Zara"
    # Nothing the customers wrote is anywhere in the database: no table holds a word of the chat.
    every_text = " ".join(
        str(v) for table in inspect(db_session.get_bind()).get_table_names() if table in ("orders", "customers")
        for row in db_session.execute(text(f"SELECT * FROM {table}")) for v in row
    )
    for phrase in ("advance transfer", "easypaisa", "bhej do", "chahiye", "book karna"):
        assert phrase not in every_text


@requires_database
def test_importing_the_same_chat_twice_adds_nothing(db_client, db_session):
    rows = [accepted(c) for c in upload(db_client, "TESTDATA_android_24h.txt", me="Shop").json()["candidates"]]
    assert db_client.post(f"{BASE}/save", json={"orders": rows}).json()["saved"] == 2
    again = db_client.post(f"{BASE}/save", json={"orders": rows}).json()
    assert again == {"saved": 0, "alreadyImported": 2, "newCustomers": 0}
    assert db_session.scalar(select(func.count()).select_from(Order)) == 2


@requires_database
def test_one_bad_order_saves_nothing_and_is_reported_by_row(db_client, db_session):
    good, other = [accepted(c) for c in upload(db_client, "TESTDATA_android_24h.txt", me="Shop").json()["candidates"]]
    response = db_client.post(f"{BASE}/save", json={"orders": [good, {**other, "products": [], "amount": 0}]})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_orders" and set(error["details"]["rows"]) == {"1"}
    assert set(error["details"]["rows"]["1"]) == {"products", "amount"}
    assert db_session.scalar(select(func.count()).select_from(Order)) == 0


@requires_database
def test_the_channel_is_always_whatsapp_and_the_phone_merges_with_an_existing_customer(db_client, db_session):
    db_session.add(Customer(external_id="CUS-9", email="z@example.com", first_name="Zara", phone_normalised="+923219876543"))
    db_session.commit()
    (zara, _imran) = upload(db_client, "TESTDATA_android_24h.txt", me="Shop").json()["candidates"]
    body = db_client.post(f"{BASE}/save", json={"orders": [{**accepted(zara), "channel": "instagram"}]}).json()
    assert body["newCustomers"] == 0
    order = db_session.scalar(select(Order))
    assert order.sales_channel == "whatsapp" and order.customer.external_id == "CUS-9"


@requires_database
def test_nothing_to_save_and_too_many_are_refused(db_client):
    assert db_client.post(f"{BASE}/save", json={"orders": []}).status_code == 422
    assert db_client.post(f"{BASE}/save", json={"orders": [{}] * 501}).status_code == 422


# --- deleting --------------------------------------------------------------------------------------------

@requires_database
def test_delete_removes_only_whatsapp_orders_and_customers_left_with_nothing(db_client, db_session):
    # An order added by hand for Zara's number, so she must survive the delete.
    db_client.post("/api/v1/orders", json={"customerName": "Zara", "phone": "0321 9876543", "city": "Karachi", "products": ["Scarf"],
                                           "amount": 500, "paymentType": "cod", "channel": "instagram"})
    candidates = upload(db_client, "TESTDATA_android_24h.txt", me="Shop").json()["candidates"]
    db_client.post(f"{BASE}/save", json={"orders": [accepted(c) for c in candidates]})
    assert db_client.get(f"{BASE}/summary").json() == {"orders": 2, "customers": 2}

    assert db_client.delete(BASE).json() == {"ordersDeleted": 2, "customersDeleted": 1}     # Imran had only WhatsApp orders
    assert db_client.get(f"{BASE}/summary").json() == {"orders": 0, "customers": 0}
    db_session.expire_all()
    assert [c.phone_normalised for c in db_session.scalars(select(Customer))] == ["+923219876543"]
    assert db_session.scalar(select(func.count()).select_from(Order)) == 1                      # the hand-made order is untouched


@requires_database
def test_imported_whatsapp_orders_appear_in_the_normal_customer_list(db_client):
    rows = [accepted(c) for c in upload(db_client, "TESTDATA_android_24h.txt", me="Shop").json()["candidates"]]
    db_client.post(f"{BASE}/save", json={"orders": rows})
    names = {c["name"] for c in db_client.get("/api/v1/customers").json()["customers"]}
    assert {"Zara", "Imran"} <= names


# --- sign-in ---------------------------------------------------------------------------------------------

@pytest.mark.real_auth
def test_sign_in_is_required_everywhere(client):
    assert client.post(f"{BASE}/parse", files={"file": ("a.txt", b"x", "text/plain")}).status_code == 401
    assert client.post(f"{BASE}/save", json={"orders": []}).status_code == 401
    assert client.get(f"{BASE}/summary").status_code == 401
    assert client.delete(BASE).status_code == 401
