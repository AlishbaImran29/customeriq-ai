"""Shipment import: reading the file, one name per courier and city, linking to orders, and what happens
to the orders. Every courier, customer, phone and amount here is made up."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.errors import ApiError
from app.main import app
from app.models import Order, Shipment
from app.services.import_files import parse_file
from app.services.shipment_import import parse_status, validate_shipments
from tests.conftest import requires_database
from tests.test_imports_api import upload

FIXTURE = Path(__file__).parent / "fixtures" / "shipments" / "TESTDATA_shipments.csv"
HEAD = "order_id,customer_id,phone,courier_name,city,booked_date,delivered_or_returned_date,status,return_reason,cod_amount,courier_fee"


def check(*lines: str, header: str = HEAD):
    return validate_shipments(parse_file("\n".join([header, *lines]).encode(), "csv"))


def send(client, text: str | bytes, name="shipments.csv"):
    data = text.encode() if isinstance(text, str) else text
    return client.post("/api/v1/shipments/import", files={"file": (name, data, "text/csv")})


# --- reading the file (no database) ---------------------------------------------------------------------

def test_the_test_file_is_marked_as_made_up_and_reads_cleanly():
    assert (FIXTURE.parent / "README.md").read_text(encoding="utf-8").startswith("# Shipment test files: TEST DATA ONLY")
    result = validate_shipments(parse_file(FIXTURE.read_bytes(), "csv"))
    assert result.errors == [] and len(result.rows) == 5
    first, second, third, fourth, fifth = result.rows
    assert (first.courier.name, first.city.name, first.status, first.cod_amount) == ("TCS", "Islamabad", "delivered", Decimal("4500.00"))
    assert (second.courier.name, second.refused, second.courier.raw) == ("TCS", True, "t.c.s")      # "t.c.s " is TCS
    assert (third.status, third.closed_date, third.city.name) == ("in_transit", None, "Lahore")
    assert (fourth.courier.name, fourth.city.name, fourth.phone, fourth.refused) == ("M&P", "Rawalpindi", "+923001234567", False)
    assert fifth.status == "lost" and first.booked_date == date(2026, 9, 1)


@pytest.mark.parametrize(
    ("text", "status"),
    [("delivered", "delivered"), ("Delivered", "delivered"), ("DLVD", "delivered"), ("received by customer", "delivered"),
     ("returned", "returned"), ("RTO", "returned"), ("refused by customer", "returned"), ("undelivered", "returned"),
     ("not delivered", "returned"), ("cancelled", "returned"), ("in transit", "in_transit"), ("in_transit", "in_transit"),
     ("out for delivery", "in_transit"), ("dispatched", "in_transit"), ("pending", "in_transit"), ("lost", "lost"), ("parcel missing", "lost"),
     ("banana", None)],
)
def test_the_words_couriers_use_for_a_status(text, status):
    assert parse_status(text) == status


def test_missing_columns_are_named():
    with pytest.raises(ApiError) as error:
        check("x", header="order_id,courier_name")
    assert error.value.details["missingColumns"] == ["booked_date", "status"]


def test_other_names_for_the_columns_are_understood():
    result = check('TCS,Lahore,01/09/2026,02/09/2026,Delivered,"1,500"', header="courier,city,booking_date,delivered_date,status,cod")
    assert result.errors == [] and result.rows[0].cod_amount == Decimal("1500.00") and result.rows[0].closed_date == date(2026, 9, 2)


def test_a_closed_shipment_needs_its_date_and_dates_must_make_sense():
    today = date.today().isoformat()
    result = check(
        ",,,TCS,Lahore,01/09/2026,,delivered,,,",                  # row 2: closed with no date
        ",,,TCS,Lahore,05/09/2026,01/09/2026,returned,,,",          # row 3: back before it was sent
        ",,,TCS,Lahore,01/09/2026,2999-01-01,delivered,,,",          # row 4: a date in the future
        ",,,TCS,Lahore,01/09/2026,,in_transit,,,",                  # row 5: fine, still on the way
        f",,,TCS,Lahore,{today},{today},delivered,,,",               # row 6: fine, same day
    )
    assert [(e.row, e.column) for e in result.errors] == [(2, "delivered_or_returned_date"), (3, "delivered_or_returned_date"), (4, "delivered_or_returned_date")]
    assert result.rejected == 3 and len(result.rows) == 2


def test_each_bad_value_is_reported_without_repeating_it():
    result = check(
        ",,,,Lahore,01/09/2026,,in_transit,,,",                    # no courier
        ",,,TCS,Lahore,not a date,,in_transit,,,",                  # bad date
        ",,,TCS,Lahore,01/09/2026,,banana,,,",                      # bad status
        ",,,TCS,Lahore,01/09/2026,,in_transit,,-5,abc",             # bad money
        ",,,TCS,Lahore,01/09/2026,,in_transit," + "x" * 501 + ",,",  # reason too long
    )
    assert [(e.row, e.column) for e in result.errors] == [(2, "courier_name"), (3, "booked_date"), (4, "status"), (5, "cod_amount"), (5, "courier_fee"), (6, "return_reason")]
    text = " ".join(e.message for e in result.errors)
    for value in ("not a date", "banana", "abc", "-5"):
        assert value not in text


def test_refused_is_found_from_the_status_or_the_reason_but_only_for_returned_parcels():
    rows = check(
        ",,,TCS,Lahore,01/09/2026,02/09/2026,refused,,,",
        ",,,TCS,Lahore,01/09/2026,02/09/2026,returned,Customer refused,,",
        ",,,TCS,Lahore,01/09/2026,02/09/2026,returned,customer ne inkar kiya,,",
        ",,,TCS,Lahore,01/09/2026,02/09/2026,returned,Address not found,,",
        ",,,TCS,Lahore,01/09/2026,02/09/2026,delivered,they first refused then accepted,,",
    ).rows
    assert [r.refused for r in rows] == [True, True, True, False, False]


def test_ids_are_stable_so_a_file_can_be_uploaded_again():
    line = "A1,,,TCS,Lahore,01/09/2026,,in_transit,,100,"
    first = check(line, line, "A2,,,TCS,Lahore,01/09/2026,,in_transit,,100,").rows
    again = check(line, line, "A2,,,TCS,Lahore,01/09/2026,,in_transit,,100,").rows
    assert [r.external_id for r in first] == [r.external_id for r in again]
    assert first[1].external_id == first[0].external_id + "-2" and len({r.external_id for r in first}) == 3
    # The id does not depend on the status, so a later upload can update it.
    changed = check("A1,,,TCS,Lahore,01/09/2026,03/09/2026,delivered,,100,").rows[0]
    assert changed.external_id == first[0].external_id


# --- saving and linking ---------------------------------------------------------------------------------

def orders(client, *rows: str):
    assert upload(client, "customer_id,email,order_id,order_date,order_value,phone\n" + "\n".join(rows)).status_code == 201


@requires_database
def test_shipments_are_saved_with_one_name_per_courier_and_city(db_client, db_session):
    body = send(db_client, FIXTURE.read_text(encoding="utf-8")).json()
    assert (body["rowsInFile"], body["created"], body["updated"], body["rejected"]) == (5, 5, 0, 0)
    saved = {s.cod_amount: s for s in db_session.scalars(select(Shipment))}
    assert {s.courier for s in saved.values()} == {"TCS", "Leopards", "M&P", "Trax"}
    tcs = saved[Decimal("3200.00")]
    assert (tcs.courier, tcs.courier_raw, tcs.city, tcs.city_raw, tcs.refused, tcs.status) == ("TCS", "t.c.s", "Islamabad", "Islamabad", True, "returned")
    assert saved[Decimal("2500.00")].city == "Rawalpindi" and saved[Decimal("2500.00")].city_raw == "pindi"
    assert tcs.source == "import" and tcs.return_reason == "Customer refused to accept" and tcs.courier_fee == Decimal("250.00")


@requires_database
def test_a_name_that_is_not_in_the_lists_is_kept_and_reported(db_client, db_session):
    body = send(db_client, f"{HEAD}\n,,,fast rider  express,Newtown city,01/09/2026,,in_transit,,,").json()
    assert body["newCourierNames"] == ["Fast Rider Express"] and body["newCityNames"] == ["Newtown City"]
    assert db_session.scalar(select(Shipment.courier)) == "Fast Rider Express"


@requires_database
def test_uploading_the_same_file_again_updates_instead_of_adding(db_client, db_session):
    assert send(db_client, f"{HEAD}\nT-1,,,TCS,Lahore,01/09/2026,,in_transit,,1000,").json()["created"] == 1
    again = send(db_client, f"{HEAD}\nT-1,,,TCS,Lahore,01/09/2026,04/09/2026,delivered,,1000,\n,,,Trax,Multan,02/09/2026,,in_transit,,500,").json()
    assert (again["created"], again["updated"]) == (1, 1)
    assert db_session.scalar(select(func.count()).select_from(Shipment)) == 2
    first = db_session.scalar(select(Shipment).where(Shipment.courier == "TCS"))
    assert (first.status, first.closed_date) == ("delivered", date(2026, 9, 4))


@requires_database
def test_a_shipment_is_linked_to_its_order_by_order_id(db_client, db_session):
    orders(db_client, "C1,a@example.com,O-1,2026-09-01,4500,")
    body = send(db_client, f"{HEAD}\nO-1,,,TCS,Lahore,02/09/2026,05/09/2026,delivered,,4500,").json()
    assert (body["linkedToOrders"], body["unlinked"], body["ordersUpdated"]) == (1, 0, 1)
    shipment, order = db_session.scalar(select(Shipment)), db_session.scalar(select(Order))
    assert shipment.order_id == order.id and shipment.customer_id == order.customer_id
    # The courier's answer became the order's real result (the label Order Risk learns from).
    assert (order.outcome, order.outcome_date, order.label_source) == ("delivered", date(2026, 9, 5), "courier data")


@requires_database
def test_returned_shipments_mark_the_order_returned_and_open_ones_change_nothing(db_client, db_session):
    orders(db_client, "C1,a@example.com,O-1,2026-09-01,100,", "C2,b@example.com,O-2,2026-09-01,200,")
    body = send(db_client, f"{HEAD}\nO-1,,,TCS,Lahore,02/09/2026,06/09/2026,returned,,100,\nO-2,,,TCS,Lahore,02/09/2026,,in_transit,,200,").json()
    assert (body["linkedToOrders"], body["ordersUpdated"]) == (2, 1)
    by_id = {o.external_id: o for o in db_session.scalars(select(Order))}
    assert (by_id["O-1"].outcome, by_id["O-1"].label_source) == ("returned", "courier data")
    assert (by_id["O-2"].outcome, by_id["O-2"].label_source) == (None, None)


@requires_database
def test_made_up_demo_shipments_never_change_an_orders_result(db_client, db_session):
    orders(db_client, "C1,a@example.com,O-1,2026-09-01,100,")
    body = send(db_client, f"{HEAD},data_source\nO-1,,,TCS,Lahore,02/09/2026,06/09/2026,returned,,100,,demo (synthetic)").json()
    assert (body["linkedToOrders"], body["ordersUpdated"]) == (1, 0)                # linked, but not a label
    order = db_session.scalar(select(Order))
    assert (order.outcome, order.outcome_date, order.label_source) == (None, None, None)


@requires_database
def test_a_result_dated_before_the_order_is_saved_but_not_given_to_the_order(db_client, db_session):
    orders(db_client, "C1,a@example.com,O-1,2026-09-10,100,")
    body = send(db_client, f"{HEAD}\nO-1,,,TCS,Lahore,08/09/2026,09/09/2026,delivered,,100,").json()
    assert (body["linkedToOrders"], body["ordersUpdated"]) == (1, 0)
    assert db_session.scalar(select(Order.outcome)) is None


@requires_database
def test_without_an_order_id_the_customer_and_the_dates_find_the_order(db_client, db_session):
    orders(db_client, "C1,a@example.com,O-1,2026-09-01,4500,0300 1234567", "C2,b@example.com,O-2,2026-09-20,900,0321 9876543")
    lines = [
        ",C1,,TCS,Lahore,02/09/2026,,in_transit,,4500,",           # customer id, 1 day after the order
        ",,0321-9876543,Trax,Lahore,21/09/2026,,in_transit,,900,",  # phone, 1 day after the order
        ",C1,,TCS,Lahore,25/09/2026,,in_transit,,4500,",            # too far from any order of C1
        ",NOBODY,,Leopards,Lahore,02/09/2026,,in_transit,,4500,",    # a customer that does not exist
    ]
    body = send(db_client, f"{HEAD}\n" + "\n".join(lines)).json()
    assert (body["created"], body["linkedToOrders"], body["unlinked"]) == (4, 2, 2)
    by_key = {(s.courier, s.booked_date): s for s in db_session.scalars(select(Shipment))}
    order_ids = {o.external_id: o.id for o in db_session.scalars(select(Order))}
    assert by_key[("TCS", date(2026, 9, 2))].order_id == order_ids["O-1"]
    assert by_key[("Trax", date(2026, 9, 21))].order_id == order_ids["O-2"]
    assert by_key[("TCS", date(2026, 9, 25))].order_id is None
    assert by_key[("TCS", date(2026, 9, 25))].customer_id is not None              # the customer is known, the order is not


@requires_database
def test_when_two_orders_fit_equally_nothing_is_guessed(db_client, db_session):
    orders(db_client, "C1,a@example.com,O-1,2026-09-01,100,", "C1,a@example.com,O-2,2026-09-03,100,")
    body = send(db_client, f"{HEAD}\n,C1,,TCS,Lahore,02/09/2026,,in_transit,,100,").json()   # one day from both orders, same amount
    assert (body["linkedToOrders"], body["unlinked"]) == (0, 1)
    # With a different amount on one of them the choice is clear.
    orders(db_client, "C2,b@example.com,O-3,2026-09-01,300,", "C2,b@example.com,O-4,2026-09-03,100,")
    assert send(db_client, f"{HEAD}\n,C2,,TCS,Lahore,02/09/2026,,in_transit,,300,").json()["linkedToOrders"] == 1
    # Several fit but one is clearly the closest.
    orders(db_client, "C3,c@example.com,O-5,2026-09-01,50,", "C3,c@example.com,O-6,2026-09-04,60,")
    assert send(db_client, f"{HEAD}\n,C3,,TCS,Lahore,02/09/2026,,in_transit,,,").json()["linkedToOrders"] == 1


@requires_database
def test_one_bad_row_does_not_stop_the_others_and_nothing_bad_is_saved(db_client, db_session):
    body = send(db_client, f"{HEAD}\n,,,TCS,Lahore,01/09/2026,,in_transit,,,\n,,,,Lahore,01/09/2026,,in_transit,,,").json()
    assert (body["created"], body["rejected"], body["errorCount"]) == (1, 1, 1)
    assert body["errors"][0]["column"] == "courier_name" and body["errors"][0]["row"] == 3
    assert db_session.scalar(select(func.count()).select_from(Shipment)) == 1


@requires_database
def test_summary_lists_the_names_in_use(db_client):
    empty = db_client.get("/api/v1/shipments/summary").json()
    assert empty["shipments"] == 0 and "TCS" in empty["couriers"] and "Islamabad" in empty["cities"]
    send(db_client, f"{HEAD}\n,,,Fast Rider,Newtown,01/09/2026,,in_transit,,,")
    body = db_client.get("/api/v1/shipments/summary").json()
    assert body["shipments"] == 1 and "Fast Rider" in body["couriers"] and "Newtown" in body["cities"]


@requires_database
def test_demo_shipments_can_be_told_apart_and_deleted_without_touching_real_ones(db_client, db_session):
    header = HEAD + ",data_source"
    send(db_client, f"{header}\n,,,TCS,Lahore,01/09/2026,,in_transit,,,,demo (synthetic)\n,,,Trax,Lahore,01/09/2026,,in_transit,,,,")
    assert db_client.get("/api/v1/shipments/summary").json()["demoShipments"] == 1
    assert db_client.delete("/api/v1/shipments/demo").json() == {"deleted": 1}
    assert [s.courier for s in db_session.scalars(select(Shipment))] == ["Trax"]


@requires_database
def test_files_that_are_not_shipments_are_refused_clearly(db_client):
    assert send(db_client, "order_id,courier_name\nO1,TCS").status_code == 422
    assert db_client.post("/api/v1/shipments/import", files={"file": ("a.txt", b"x", "text/plain")}).status_code == 415


@pytest.mark.real_auth
def test_sign_in_is_required():
    client = TestClient(app)
    assert client.post("/api/v1/shipments/import", files={"file": ("a.csv", b"x", "text/csv")}).status_code == 401
    assert client.get("/api/v1/shipments/summary").status_code == 401
    assert client.delete("/api/v1/shipments/demo").status_code == 401
