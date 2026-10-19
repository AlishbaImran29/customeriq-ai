"""Quick Order Entry: checking what was typed, finding the customer by phone, saving the order.

All names, numbers and orders here are made up for the tests.
"""

import re
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models import Customer, Order
from app.services.quick_order import check_quick_order
from tests.conftest import requires_database


def good(**changes):
    """A complete, valid form (camelCase, as the page sends it)."""
    form = {
        "customerName": "Ayesha Khan", "phone": "0300-1234567", "city": "Lahore",
        "products": ["Red lawn suit", "Dupatta"], "amount": 4500, "paymentType": "cod",
        "channel": "instagram", "orderDate": None, "note": None,
    }
    form.update(changes)
    return form


def problems(**changes):
    clean, errors = check_quick_order(good(**changes))
    assert clean is None
    return errors


# --- checking (no database) ---------------------------------------------------------------------

def test_a_complete_form_is_clean():
    clean, errors = check_quick_order(good())
    assert errors == {}
    assert (clean.customer_name, clean.phone, clean.city) == ("Ayesha Khan", "+923001234567", "Lahore")
    assert clean.products == ["Red lawn suit", "Dupatta"] and str(clean.amount) == "4500.00"
    assert (clean.payment_type, clean.channel, clean.note) == ("cod", "instagram", None)
    assert clean.order_date == datetime.now(timezone.utc).date()          # the date defaults to today


def test_every_missing_field_is_reported_at_once_with_a_plain_message():
    clean, errors = check_quick_order({})
    assert clean is None
    assert set(errors) == {"customerName", "phone", "city", "products", "amount", "paymentType", "channel"}
    assert errors["phone"] == "Enter the customer's phone number."


@pytest.mark.parametrize("phone", ["12345", "0300-ABC4567", "+44 7911 123456", "042 35761234"])
def test_a_phone_that_is_not_a_pakistani_mobile_is_explained(phone):
    assert "Pakistani mobile number" in problems(phone=phone)["phone"]


@pytest.mark.parametrize(
    ("amount", "message"),
    [(0, "more than 0"), (-5, "more than 0"), ("abc", "as a number"), ("", "Enter the amount"), (None, "Enter the amount"),
     (10**9, "too large"), (float("nan"), "as a number"), (True, "as a number"), ([1], "as a number")],
)
def test_amounts_that_cannot_be_real_are_refused(amount, message):
    assert message in problems(amount=amount)["amount"]


@pytest.mark.parametrize(("typed", "saved"), [("2,500", "2500.00"), (" 99.999 ", "100.00"), (1500.5, "1500.50"), ("2500", "2500.00")])
def test_amounts_are_cleaned(typed, saved):
    clean, errors = check_quick_order(good(amount=typed))
    assert errors == {} and str(clean.amount) == saved


def test_products_are_trimmed_and_repeats_dropped_and_none_means_an_error():
    clean, _ = check_quick_order(good(products=["  Kurta ", "kurta", "", "Scarf"]))
    assert clean.products == ["Kurta", "Scarf"]
    assert problems(products=[])["products"] == "Add at least one product."
    assert problems(products=["", "  "])["products"] == "Add at least one product."
    assert problems(products="Kurta")["products"] == "Add at least one product."     # must be a list
    assert "at most 20" in problems(products=[f"P{i}" for i in range(21)])["products"]
    assert "too long" in problems(products=["x" * 101])["products"]


def test_payment_type_and_channel_must_be_one_of_the_allowed_values():
    assert problems(paymentType="cash")["paymentType"] == "Choose COD or prepaid."
    assert problems(channel="tiktok")["channel"] == "Choose where the order came from."
    clean, errors = check_quick_order(good(paymentType="PREPAID", channel="WhatsApp"))
    assert errors == {} and (clean.payment_type, clean.channel) == ("prepaid", "whatsapp")


def test_dates():
    today = datetime.now(timezone.utc).date()
    assert check_quick_order(good(orderDate=(today - timedelta(days=3)).isoformat()))[1] == {}
    assert check_quick_order(good(orderDate=(today + timedelta(days=1)).isoformat()))[1] == {}       # one day of slack
    assert problems(orderDate=(today + timedelta(days=2)).isoformat())["orderDate"] == "The date is in the future."
    assert "YYYY-MM-DD" in problems(orderDate="18/10/2026")["orderDate"]
    assert "too far" in problems(orderDate="1999-12-31")["orderDate"]


def test_long_names_cities_and_notes_are_refused():
    assert "too long" in problems(customerName="x" * 101)["customerName"]
    assert "too long" in problems(city="x" * 101)["city"]
    assert "too long" in problems(note="x" * 501)["note"]
    assert check_quick_order(good(note="  Call before delivery  "))[0].note == "Call before delivery"


# --- saving ---------------------------------------------------------------------------------------

def post(client, **changes):
    return client.post("/api/v1/orders", json=good(**changes))


@requires_database
def test_a_new_customer_and_order_are_saved(db_client, db_session):
    response = post(db_client, note="Call before delivery")
    assert response.status_code == 201, response.text
    body = response.json()
    assert re.fullmatch(r"QO-\d{8}-[A-Z2-9]{5}", body["orderId"])
    assert (body["customerId"], body["phone"], body["customerName"]) == ("+923001234567", "+923001234567", "Ayesha Khan")
    assert body["returning"] is False and body["customerOrders"] == 1

    customer = db_session.scalar(select(Customer))
    assert customer.email is None and customer.phone_normalised == "+923001234567" and customer.first_name == "Ayesha Khan"
    order = db_session.scalar(select(Order))
    assert order.external_id == body["orderId"] and order.customer_id == customer.id
    assert (order.sales_channel, order.channel, order.payment_type) == ("instagram", "Instagram", "cod")
    assert (order.city, order.products, order.note) == ("Lahore", "Red lawn suit, Dupatta", "Call before delivery")
    assert str(order.order_value) == "4500.00"


@requires_database
def test_the_same_phone_in_another_format_is_the_same_customer(db_client, db_session):
    post(db_client)
    second = post(db_client, phone="+92 300 1234567", customerName="A. Khan", amount=1200, channel="whatsapp", paymentType="prepaid")
    assert second.status_code == 201
    body = second.json()
    assert body["returning"] is True and body["customerOrders"] == 2 and body["customerName"] == "Ayesha Khan"   # name kept
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 1
    assert db_session.scalar(select(func.count()).select_from(Order)) == 2


@requires_database
def test_a_customer_whose_id_was_the_number_is_found_and_gets_the_phone_key(db_client, db_session):
    db_session.add(Customer(external_id="+923001234567", email=None))        # e.g. from an old file
    db_session.commit()
    body = post(db_client).json()
    assert body["returning"] is True
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 1
    assert db_session.scalar(select(Customer.phone_normalised)) == "+923001234567"


@requires_database
def test_problems_come_back_together_as_fields_and_nothing_is_saved(db_client, db_session):
    response = post(db_client, phone="12345", amount=0, products=[], channel="tiktok")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_order"
    assert set(error["details"]["fields"]) == {"phone", "amount", "products", "channel"}
    assert db_session.scalar(select(func.count()).select_from(Order)) == 0
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 0


@requires_database
def test_pressing_save_twice_does_not_add_the_order_twice(db_client, db_session):
    assert post(db_client).status_code == 201
    again = post(db_client)
    assert again.status_code == 409 and again.json()["error"]["code"] == "duplicate_order"
    assert post(db_client, amount=4600).status_code == 201                    # a different order is fine
    assert db_session.scalar(select(func.count()).select_from(Order)) == 2


@requires_database
def test_the_date_can_be_set_and_defaults_to_today(db_client, db_session):
    post(db_client, orderDate="2026-10-01")
    post(db_client, amount=100)
    dates = sorted(db_session.scalars(select(Order.order_date)))
    assert dates[0] == date(2026, 10, 1) and dates[1] == datetime.now(timezone.utc).date()


@requires_database
def test_quick_orders_appear_in_the_customers_list_without_an_email(db_client):
    post(db_client)
    customers = db_client.get("/api/v1/customers").json()["customers"]
    assert customers[0]["name"] == "Ayesha Khan" and customers[0]["email"] is None
    assert customers[0]["channel"] == "Instagram" and customers[0]["orders"] == 1


# --- looking a customer up while typing ------------------------------------------------------------

@requires_database
def test_lookup_says_whether_the_number_is_valid_and_who_it_belongs_to(db_client):
    unfinished = db_client.get("/api/v1/customers/lookup", params={"phone": "0300-12"}).json()
    assert unfinished["valid"] is False and unfinished["found"] is False

    new = db_client.get("/api/v1/customers/lookup", params={"phone": "03001234567"}).json()
    assert new == {"valid": True, "phone": "+923001234567", "found": False, "name": None,
                   "orders": 0, "lastOrderDate": None, "lastCity": None}

    post(db_client, orderDate="2026-10-01", city="Lahore")
    post(db_client, orderDate="2026-10-05", city="Karachi", amount=900)
    post(db_client, orderDate="2026-10-09", city="Multan", amount=700, phone="+92 300 1234567")
    known = db_client.get("/api/v1/customers/lookup", params={"phone": "300 1234567"}).json()
    assert known["found"] is True and known["name"] == "Ayesha Khan" and known["orders"] == 3
    assert known["lastOrderDate"] == "2026-10-09" and known["lastCity"] == "Multan"


@pytest.mark.real_auth
def test_sign_in_is_required():
    client = TestClient(app)
    assert client.post("/api/v1/orders", json=good()).status_code == 401
    assert client.get("/api/v1/customers/lookup", params={"phone": "0300"}).status_code == 401
