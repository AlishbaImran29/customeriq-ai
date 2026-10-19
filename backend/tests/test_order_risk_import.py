"""Order Risk Check data: the optional import columns, the UCI cancellation link, courier files."""

import csv
import importlib.util
import io
from datetime import date, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.models import Customer, Order
from app.services.import_files import parse_file
from app.services.import_validation import has_house_number, is_valid_phone, validate_rows
from app.services.order_risk_data import load_order_inputs
from tests.conftest import requires_database
from tests.test_imports_api import upload

HEAD = "customer_id,email,order_id,order_date,order_value"


def validate(extra_header: str, *rows: str):
    text = "\n".join([f"{HEAD},{extra_header}", *rows])
    return validate_rows(parse_file(text.encode(), "csv"))


# --- optional columns -------------------------------------------------------------

def test_files_without_the_new_columns_still_import_with_empty_risk_facts():
    result = validate_rows(parse_file(f"{HEAD}\nC1,a@example.com,O1,2026-01-05,10".encode(), "csv"))
    row = result.rows[0]
    assert result.errors == []
    assert (row.ordered_at, row.item_count, row.outcome, row.label_source, row.phone_valid) == (None,) * 5


def test_risk_columns_are_read_and_the_address_is_reduced_to_checks():
    result = validate(
        "order_datetime,item_count,distinct_products,phone,address",
        "C1,a@example.com,O1,2026-01-05,10,2026-01-05 14:30,5,3,0300 1234567,House 12 Street 4",
        "C1,a@example.com,O2,2026-01-06,10,,,,12345,Near the market",
    )
    assert result.errors == []
    a, b = result.rows
    assert a.ordered_at == datetime(2026, 1, 5, 14, 30) and (a.item_count, a.distinct_products) == (5, 3)
    assert a.phone_valid is True and a.has_house_number is True and a.address_length == len("House 12 Street 4")
    assert b.phone_valid is False and b.has_house_number is False and b.ordered_at is None
    assert not hasattr(a, "address")  # the text itself is not kept


def test_outcome_rules_and_error_messages_do_not_echo_values():
    result = validate(
        "outcome,outcome_date,phone",
        "C1,a@example.com,O1,2026-01-05,10,returned,,",                  # returned needs a date
        "C1,a@example.com,O2,2026-01-05,10,delivered,2026-01-01,",       # date before the order
        "C1,a@example.com,O3,2026-01-05,10,lost,,",                      # unknown status
        "C1,a@example.com,O4,2026-01-05,10,returned,2026-01-09,",        # fine
        "C1,a@example.com,O5,2026-01-05,10,,,03001234567890123456789012345678901234567890",  # too long
    )
    assert [(e.row, e.column) for e in result.errors] == [
        (2, "outcome_date"), (3, "outcome_date"), (4, "outcome"), (6, "phone"),
    ]
    assert all("lost" not in e.message and "0300" not in e.message for e in result.errors)
    good = result.rows[0]
    assert (good.outcome, good.outcome_date, good.label_source) == ("returned", date(2026, 1, 9), "courier data")


def test_time_of_day_must_match_the_order_date_and_counts_must_make_sense():
    result = validate(
        "order_datetime,item_count,distinct_products",
        "C1,a@example.com,O1,2026-01-05,10,2026-01-06 09:00,,",   # a different day
        "C1,a@example.com,O2,2026-01-05,10,,2,5",                  # more products than items
        "C1,a@example.com,O3,2026-01-05,10,,0,",                   # zero items
    )
    assert [e.column for e in result.errors] == ["order_datetime", "distinct_products", "item_count"]


def test_phone_and_address_checks():
    assert is_valid_phone("0300 1234567") and is_valid_phone("+92-300-1234567")
    assert not is_valid_phone("12345") and not is_valid_phone("abc")
    assert has_house_number("H# 12, Block B") and not has_house_number("Near the market")


# --- UCI converter: credit notes are linked to the order they cancelled ---------------

_spec = importlib.util.spec_from_file_location(
    "convert_uci_online_retail",
    Path(__file__).resolve().parents[1] / "scripts" / "convert_uci_online_retail.py",
)
convert_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(convert_module)
HEADER = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]


@pytest.fixture
def linked_workbook(tmp_path):
    wb = Workbook()
    sheet = wb.active
    sheet.append(HEADER)
    uk = "United Kingdom"
    sheet.append([100001, "A1", "GLASS", 4, datetime(2010, 1, 5, 9, 30), 5.0, 13085, uk])     # later cancelled
    sheet.append([100001, "B2", "LIGHT", 1, datetime(2010, 1, 5, 9, 30), 10.0, 13085, uk])
    sheet.append([100002, "A1", "GLASS", 2, datetime(2010, 2, 1, 11, 0), 5.0, 13085, uk])     # newer order, same product
    sheet.append(["C100003", "A1", "GLASS", -2, datetime(2010, 2, 10, 15, 0), 5.0, 13085, uk])  # cancels 100002 (most recent)
    sheet.append(["C100004", "ZZ", "UNKNOWN", -1, datetime(2010, 2, 11, 9, 0), 1.0, 13085, uk])  # matches nothing
    sheet.append([100005, "C3", "PLATE", 1, datetime(2010, 3, 1, 8, 0), 7.5, 14000, uk])        # never cancelled
    path = tmp_path / "linked.xlsx"
    wb.save(path)
    return path


def test_a_credit_note_marks_the_most_recent_earlier_order_with_that_product(linked_workbook):
    rows, stats = convert_module.convert(linked_workbook)
    orders = {r["order_id"]: r for r in rows}

    assert set(orders) == {"PUB-100001", "PUB-100002", "PUB-100005"}   # credit notes are not orders
    assert orders["PUB-100002"]["outcome"] == "returned" and orders["PUB-100002"]["outcome_date"] == "2010-02-10"
    assert orders["PUB-100001"]["outcome"] == "delivered" and orders["PUB-100001"]["outcome_date"] == ""
    assert orders["PUB-100005"]["outcome"] == "delivered"
    assert all(r["label_source"] == "proxy: cancellations" for r in rows)
    assert (stats["cancellations_linked"], stats["cancellations_unlinked"], stats["orders_returned"]) == (1, 1, 1)

    first = orders["PUB-100001"]
    assert first["order_datetime"] == "2010-01-05 09:30:00"
    assert (first["item_count"], first["distinct_products"]) == (5, 2)


def test_converted_rows_pass_the_real_import_validator(linked_workbook):
    rows, _ = convert_module.convert(linked_workbook)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    result = validate_rows(parse_file(buffer.getvalue().encode(), "csv"))
    assert result.errors == [] and len(result.rows) == 3
    assert {r.outcome for r in result.rows} == {"delivered", "returned"}


# --- saving, and the courier status file ------------------------------------------------

@requires_database
def test_import_saves_risk_facts_and_a_plain_reimport_keeps_them(db_client, db_session):
    full = (
        f"{HEAD},order_datetime,item_count,distinct_products,outcome,outcome_date,label_source,phone,address\n"
        "C1,a@example.com,O1,2026-01-05,10,2026-01-05 14:30,5,3,returned,2026-01-09,proxy: cancellations,0300 1234567,House 12\n"
    )
    assert upload(db_client, full).status_code == 201
    order = db_session.scalar(select(Order).where(Order.external_id == "O1"))
    assert order.ordered_at == datetime(2026, 1, 5, 14, 30) and order.item_count == 5
    assert (order.outcome, order.outcome_date, order.label_source) == ("returned", date(2026, 1, 9), "proxy: cancellations")
    assert order.has_house_number is True and order.phone_valid is True
    assert db_session.scalar(select(Customer.phone)) == "0300 1234567"

    # The same order again, with no risk columns: nothing is erased.
    assert upload(db_client, f"{HEAD}\nC1,a@example.com,O1,2026-01-05,12").status_code == 201
    db_session.expire_all()
    again = db_session.scalar(select(Order).where(Order.external_id == "O1"))
    assert again.order_value == 12 and again.outcome == "returned" and again.item_count == 5


def courier(client, *rows: str):
    text = "\n".join(["order_id,customer_id,status,date", *rows])
    return client.post("/api/v1/imports/courier", files={"file": ("courier.csv", text.encode(), "text/csv")})


@requires_database
def test_courier_file_sets_real_outcomes_and_rejects_bad_rows(db_client, db_session):
    plain = "\n".join([
        HEAD,
        "C1,a@example.com,O1,2026-01-05,10",
        "C1,a@example.com,O2,2026-01-06,10",
        "C2,b@example.com,O3,2026-01-07,10",
    ])
    assert upload(db_client, plain).status_code == 201

    response = courier(
        db_client,
        "O1,C1,delivered,2026-01-09",
        "O2,C1,RTO,2026-01-12",           # a courier "return to origin" counts as returned
        "O3,C1,returned,2026-01-12",      # O3 belongs to C2
        "O9,C1,returned,2026-01-12",      # no such order
        "O1,C1,lost,2026-01-12",          # unknown status
        "O2,C1,returned,2026-01-13",      # O2 already appeared above in this file
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["rowsInFile"], body["rowsUpdated"], body["rowsReturned"], body["rowsRejected"]) == (6, 2, 1, 4)
    assert [(e["row"], e["column"]) for e in body["errors"]] == [
        (4, "customer_id"), (5, "order_id"), (6, "status"), (7, "order_id"),
    ]

    db_session.expire_all()
    o1, o2 = (db_session.scalar(select(Order).where(Order.external_id == i)) for i in ("O1", "O2"))
    assert (o1.outcome, o1.outcome_date, o1.label_source) == ("delivered", date(2026, 1, 9), "courier data")
    assert (o2.outcome, o2.outcome_date) == ("returned", date(2026, 1, 12))   # RTO row: the first one counts


@requires_database
def test_courier_file_replaces_a_proxy_label_and_features_use_it(db_client, db_session):
    proxy = f"{HEAD},outcome,outcome_date,label_source\nC1,a@example.com,O1,2026-01-05,10,delivered,,proxy: cancellations\n"
    assert upload(db_client, proxy).status_code == 201
    assert courier(db_client, "O1,C1,returned,2026-01-08").json()["rowsReturned"] == 1
    db_session.expire_all()
    inputs = {o.order_id: o for o in load_order_inputs(db_session)}
    assert inputs["O1"].outcome == "returned" and inputs["O1"].outcome_date == date(2026, 1, 8)
    assert db_session.scalar(select(Order.label_source)) == "courier data"


def test_courier_file_needs_its_columns(client_without_db):
    response = client_without_db.post(
        "/api/v1/imports/courier", files={"file": ("c.csv", b"order_id,status\nO1,returned", "text/csv")}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "missing_columns"


@pytest.fixture
def client_without_db():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)
