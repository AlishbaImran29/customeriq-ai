"""Social Seller Mode, step 1: customers known by phone number, an optional email, clean channels.

All names, numbers and orders here are made up for the tests.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import Customer, Order
from app.services.customer_identity import assign_customers_by_phone
from app.services.import_files import parse_file
from app.services.import_validation import OrderRow, validate_rows
from tests.conftest import requires_database
from tests.test_imports_api import upload

SOCIAL = "order_id,order_date,order_value,phone,channel,first_name"


def customer_count(db):
    return db.scalar(select(func.count()).select_from(Customer))


# --- the merge rule, on its own (no database) -----------------------------------------------

def row(customer_id: str, phone: str | None, order_id: str = "O") -> OrderRow:
    return OrderRow(
        row=2, customer_id=customer_id, email=None, order_id=order_id, order_date=date(2026, 1, 1),
        order_value=Decimal(1), first_name=None, last_name=None, country=None, product_category=None,
        channel=None, engagement=None, phone_normalised=phone,
    )


def test_the_same_phone_means_the_same_customer():
    rows = [row("A", "+923001234567", "O1"), row("B", "+923001234567", "O2"), row("C", "+923219876543", "O3")]
    merged, count = assign_customers_by_phone(rows, {})
    assert [r.customer_id for r in merged] == ["A", "A", "C"]     # the first customer seen owns the number
    assert count == 1


def test_a_number_that_is_already_saved_keeps_its_owner():
    merged, count = assign_customers_by_phone([row("NEW", "+923001234567")], {"+923001234567": "OLD"})
    assert merged[0].customer_id == "OLD" and count == 1


def test_rows_without_a_phone_are_left_alone():
    merged, count = assign_customers_by_phone([row("A", None), row("B", None)], {"+923001234567": "OLD"})
    assert [r.customer_id for r in merged] == ["A", "B"] and count == 0


# --- validation -----------------------------------------------------------------------------

def validate(header: str, *lines: str):
    return validate_rows(parse_file("\n".join([header, *lines]).encode(), "csv"))


def test_a_row_needs_a_customer_id_an_email_or_a_phone():
    result = validate(
        "order_id,order_date,order_value,customer_id,email,phone",
        "O1,2026-01-01,10,C1,,",                       # id only
        "O2,2026-01-01,10,,a@example.com,",            # email only
        "O3,2026-01-01,10,,,0300 1234567",             # phone only
        "O4,2026-01-01,10,,,",                         # nobody
        "O5,2026-01-01,10,,,98765",                    # a phone that is not a Pakistani mobile: nobody
    )
    assert [r.order_id for r in result.rows] == ["O1", "O2", "O3"]
    assert [r.customer_id for r in result.rows] == ["C1", "a@example.com", "+923001234567"]
    assert [(e.row, e.column) for e in result.errors] == [(5, "customer_id"), (6, "phone")]
    assert all("98765" not in e.message for e in result.errors)


def test_a_phone_that_is_not_pakistani_does_not_reject_a_row_that_has_another_id():
    row_ = validate(
        "order_id,order_date,order_value,customer_id,phone", "O1,2026-01-01,10,C1,+44 7911 123456"
    ).rows[0]
    assert row_.customer_id == "C1" and row_.phone_normalised is None and row_.phone_valid is True


def test_channel_text_becomes_a_clean_channel_only_when_given():
    rows = validate(
        "order_id,order_date,order_value,customer_id,channel",
        "O1,2026-01-01,10,C1,insta dm", "O2,2026-01-01,10,C1,", "O3,2026-01-01,10,C1,Daraz",
    ).rows
    assert [r.sales_channel for r in rows] == ["instagram", None, "other"]


# --- saving and merging -----------------------------------------------------------------------

@requires_database
def test_orders_with_only_a_phone_create_customers_without_an_email(db_client, db_session):
    response = upload(db_client, "\n".join([
        SOCIAL,
        "O1,2026-01-05,1500,0300-1234567,Instagram,Ayesha",
        "O2,2026-01-09,2500,+92 300 1234567,whatsapp,",
        "O3,2026-01-10,800,0321 9876543,fb,Bilal",
    ]))
    assert response.status_code == 201, response.text
    assert customer_count(db_session) == 2                      # 0300-1234567 and +92 300 1234567 are one person
    ayesha = db_session.scalar(select(Customer).where(Customer.phone_normalised == "+923001234567"))
    assert ayesha.email is None and ayesha.first_name == "Ayesha" and ayesha.external_id == "+923001234567"
    orders = {o.external_id: o for o in db_session.scalars(select(Order))}
    assert orders["O1"].customer_id == orders["O2"].customer_id != orders["O3"].customer_id
    assert [orders[k].sales_channel for k in ("O1", "O2", "O3")] == ["instagram", "whatsapp", "facebook"]


@requires_database
def test_a_phone_number_finds_the_customer_from_an_earlier_import(db_client, db_session):
    upload(db_client, "customer_id,email,order_id,order_date,order_value,phone\nCUS-1,a@example.com,O1,2026-01-01,10,03001234567")
    upload(db_client, f"{SOCIAL}\nO2,2026-02-01,20,+92 300 1234567,instagram,")
    assert customer_count(db_session) == 1
    assert {o.customer_id for o in db_session.scalars(select(Order))} == {db_session.scalar(select(Customer.id))}
    customer = db_session.scalar(select(Customer))
    assert customer.external_id == "CUS-1" and customer.email == "a@example.com"   # nothing was overwritten


@requires_database
def test_two_ids_with_the_same_phone_in_one_file_become_one_customer(db_client, db_session):
    upload(db_client, "\n".join([
        "customer_id,order_id,order_date,order_value,phone",
        "A,O1,2026-01-01,10,0300 1234567", "B,O2,2026-01-02,10,3001234567",
    ]))
    assert customer_count(db_session) == 1
    assert db_session.scalar(select(Customer.external_id)) == "A"


@requires_database
def test_an_existing_customer_gets_their_normalised_phone_when_it_first_appears(db_client, db_session):
    upload(db_client, "customer_id,email,order_id,order_date,order_value\nC1,a@example.com,O1,2026-01-01,10")
    assert db_session.scalar(select(Customer.phone_normalised)) is None
    upload(db_client, "customer_id,order_id,order_date,order_value,phone\nC1,O2,2026-01-02,10,0300-1234567")
    db_session.expire_all()
    assert db_session.scalar(select(Customer.phone_normalised)) == "+923001234567"


@requires_database
def test_old_style_files_work_exactly_as_before(db_client, db_session):
    response = upload(db_client, "customer_id,email,order_id,order_date,order_value,channel\nC1,A@Example.com,O1,2026-01-01,10,Shopify (web)")
    assert response.status_code == 201 and response.json()["rowsImported"] == 1
    customer, order = db_session.scalar(select(Customer)), db_session.scalar(select(Order))
    assert customer.email == "a@example.com" and customer.phone_normalised is None
    assert order.channel == "Shopify (web)" and order.sales_channel == "website"


@requires_database
def test_a_plain_reimport_does_not_erase_the_channel_or_the_email(db_client, db_session):
    upload(db_client, "customer_id,email,order_id,order_date,order_value,channel\nC1,a@example.com,O1,2026-01-01,10,instagram")
    upload(db_client, "customer_id,order_id,order_date,order_value\nC1,O1,2026-01-01,12")
    db_session.expire_all()
    order, customer = db_session.scalar(select(Order)), db_session.scalar(select(Customer))
    assert order.order_value == 12 and order.sales_channel == "instagram" and customer.email == "a@example.com"


@requires_database
def test_a_file_that_says_nothing_about_who_ordered_is_refused(db_client, db_session):
    response = upload(db_client, "order_id,order_date,order_value\nO1,2026-01-01,10")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "missing_columns" and "customer_id or email or phone" in error["details"]["missingColumns"][0]
    assert customer_count(db_session) == 0


@requires_database
def test_the_customers_list_works_for_a_customer_without_an_email(db_client):
    upload(db_client, f"{SOCIAL}\nO1,2026-01-05,1500,0300-1234567,whatsapp,Ayesha")
    body = db_client.get("/api/v1/customers").json()
    assert body["customers"][0]["email"] is None and body["customers"][0]["name"] == "Ayesha"


@requires_database
def test_the_database_allows_only_one_customer_per_phone_number(db_session):
    db_session.add(Customer(external_id="X", phone_normalised="+923001234567"))
    db_session.commit()
    db_session.add(Customer(external_id="Y", phone_normalised="+923001234567"))
    with pytest.raises(Exception):  # the unique index refuses a second customer with the same number
        db_session.commit()
    db_session.rollback()
