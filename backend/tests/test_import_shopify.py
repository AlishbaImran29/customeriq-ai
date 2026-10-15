"""Shopify orders export: detection and conversion (made-up example data)."""

import csv
import io
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models import Order
from app.services.import_files import parse_file
from app.services.import_formats import convert, detect_format
from app.services.import_validation import validate_rows
from tests.conftest import requires_database

# Header list from Shopify's "Exporting orders" help page (Phone appears twice there too).
SHOPIFY_HEADERS = [
    "Name", "Phone", "Email", "Financial Status", "Paid at", "Fulfillment Status", "Fulfilled at",
    "Accepts Marketing", "Currency", "Subtotal", "Shipping", "Taxes", "Total", "Discount Code",
    "Discount Amount", "Shipping Method", "Created at", "Lineitem quantity", "Lineitem name",
    "Lineitem price", "Lineitem compare-at price", "Lineitem SKU", "Lineitem requires shipping",
    "Lineitem taxable", "Lineitem fulfillment status", "Billing Name", "Billing Street",
    "Billing Address1", "Billing Address2", "Billing Company", "Billing City", "Billing Zip",
    "Billing Province", "Billing Province Name", "Billing Country", "Billing Phone", "Shipping Name",
    "Shipping Street", "Shipping Address1", "Shipping Address2", "Shipping Company", "Shipping City",
    "Shipping Zip", "Shipping Province", "Shipping Province Name", "Shipping Country", "Shipping Phone",
    "Notes", "Note Attributes", "Canceled at", "Payment Method", "Payment Reference (deprecated)",
    "Payment References", "Refunded Amount", "Vendor", "Outstanding Balance", "Employee", "Location",
    "Device ID", "Id", "Tags", "Risk Level", "Source", "Lineitem discount", "Tax 1 Name",
    "Tax 1 Value", "Phone", "Payment ID", "Payment terms", "Next payment due at",
]


def shopify_csv(orders: list[dict]) -> bytes:
    """Each dict is one row; keys are Shopify header names."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(SHOPIFY_HEADERS)
    for row in orders:
        writer.writerow([row.get(h, "") for h in SHOPIFY_HEADERS])
    return buffer.getvalue().encode("utf-8")


ORDERS = [
    # #1001: two line items; the second row leaves order fields blank.
    {"Name": "#1001", "Email": "Amelia.Demo@Example.com", "Financial Status": "paid", "Total": "150.00",
     "Created at": "2026-09-14 10:22:05 -0400", "Lineitem name": "Serum", "Billing Name": "Amelia Demo",
     "Billing Country": "US", "Source": "web"},
    {"Name": "#1001", "Lineitem name": "Cleanser"},
    # #1002: same customer, different email case.
    {"Name": "#1002", "Email": "amelia.demo@example.com", "Financial Status": "paid", "Total": "40.00",
     "Created at": "2026-10-01 08:00:00 -0400", "Billing Name": "Amelia Demo", "Source": "pos"},
    # #1003: canceled -> skipped.
    {"Name": "#1003", "Email": "noah@example.com", "Financial Status": "voided", "Total": "60.00",
     "Created at": "2026-10-02 09:00:00 -0400", "Canceled at": "2026-10-02 10:00:00 -0400"},
    # #1004: fully refunded -> skipped.
    {"Name": "#1004", "Email": "noah@example.com", "Financial Status": "refunded", "Total": "25.00",
     "Created at": "2026-10-03 09:00:00 -0400"},
    # #1005: partially refunded -> 80 - 30 = 50.
    {"Name": "#1005", "Email": "liam@example.com", "Financial Status": "partially_refunded", "Total": "80.00",
     "Refunded Amount": "30.00", "Created at": "2026-10-04 09:00:00 -0400", "Billing Name": "Liam"},
    # #1006: no email (e.g. walk-in POS sale) -> rejected by validation.
    {"Name": "#1006", "Financial Status": "paid", "Total": "15.00", "Created at": "2026-10-05 09:00:00 -0400"},
]


def test_detects_shopify_and_standard_formats():
    assert detect_format(SHOPIFY_HEADERS) == "shopify"
    assert detect_format(["customer_id", "email", "order_id", "order_date", "order_value"]) == "standard"


def test_shopify_conversion_groups_line_items_and_skips_canceled_orders():
    parsed = parse_file(shopify_csv(ORDERS), "csv")
    assert len(parsed.rows) == 7  # line-item rows in the file

    converted = convert(parsed)
    assert converted.file_format == "shopify"
    assert [(e.row, e.message) for e in converted.skipped] == [
        (5, "Skipped: the order was canceled."),
        (6, "Skipped: the order was fully refunded."),
    ]

    result = validate_rows(converted.parsed)
    rows = {r.order_id: r for r in result.rows}
    assert set(rows) == {"#1001", "#1002", "#1005"}
    first = rows["#1001"]
    assert first.customer_id == first.email == "amelia.demo@example.com"
    assert rows["#1002"].customer_id == "amelia.demo@example.com"  # same customer
    assert first.order_date == date(2026, 9, 14) and first.order_value == Decimal("150.00")
    assert (first.first_name, first.last_name, first.country) == ("Amelia", "Demo", "US")
    assert first.channel == "Shopify (web)" and rows["#1002"].channel == "Shopify (pos)"
    assert rows["#1005"].order_value == Decimal("50.00")  # partial refund removed
    assert [(e.row, e.column) for e in result.errors] == [(8, "customer_id"), (8, "email")]


@requires_database
def test_shopify_upload_end_to_end(db_client, db_session):
    response = db_client.post(
        "/api/v1/imports",
        files={"file": ("orders_export.csv", shopify_csv(ORDERS), "text/csv")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["fileFormat"] == "shopify" and body["rowsInFile"] == 7
    assert (body["rowsReceived"], body["rowsImported"], body["rowsRejected"]) == (6, 3, 3)
    assert db_session.scalars(select(Order.external_id).order_by(Order.external_id)).all() == [
        "#1001", "#1002", "#1005",
    ]
