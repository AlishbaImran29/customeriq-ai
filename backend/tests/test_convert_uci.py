"""The UCI Online Retail II converter, on a tiny made-up workbook (no download needed)."""

import csv
import importlib.util
import io
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.services.import_files import parse_file
from app.services.import_validation import validate_rows

_spec = importlib.util.spec_from_file_location(
    "convert_uci_online_retail",
    Path(__file__).resolve().parents[1] / "scripts" / "convert_uci_online_retail.py",
)
convert_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(convert_module)

HEADER = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]


@pytest.fixture
def workbook_path(tmp_path):
    wb = Workbook()
    first = wb.active
    first.title = "Year 2009-2010"
    first.append(HEADER)
    jan = datetime(2010, 1, 5, 9, 30)
    first.append([100001, 85048, "GLASS BALL", 12, jan, 2.50, 13085, "United Kingdom"])      # 30.00
    first.append([100001, "79323P", "PINK LIGHTS", 2, jan, 10.00, 13085, "United Kingdom"])  # 20.00
    first.append([100001, "POST", "POSTAGE", 1, jan, 18.00, 13085, "United Kingdom"])        # not merchandise
    first.append(["C100002", 85048, "GLASS BALL", -1, jan, 2.50, 13085, "United Kingdom"])   # cancellation
    first.append([100003, 85048, "GLASS BALL", 5, jan, 1.00, None, "United Kingdom"])        # guest checkout
    first.append([100004, "X1", "FREE GIFT", 3, jan, 0.0, 14000, "United Kingdom"])          # zero price
    first.append([100005, "A1", "WIDGET", 1, datetime(2010, 12, 2, 10, 0), 10.0, 15000, "France"])
    second = wb.create_sheet("Year 2010-2011")
    second.append(HEADER)
    second.append([100005, "A1", "WIDGET", 1, datetime(2010, 12, 2, 10, 0), 10.0, 15000, "France"])  # overlap
    second.append([100006, "B1", "GADGET", 2, datetime(2011, 3, 3, 8, 0), 4.25, 15000.0, "France"])  # float id
    path = tmp_path / "online_retail_test.xlsx"
    wb.save(path)
    return path


def test_orders_are_built_with_the_documented_rules(workbook_path):
    rows, stats = convert_module.convert(workbook_path)
    orders = {r["order_id"]: r for r in rows}

    assert set(orders) == {"PUB-100001", "PUB-100005", "PUB-100006"}
    first = orders["PUB-100001"]
    assert first["customer_id"] == "PUB-13085" and first["email"] == "pub-13085@example.com"
    assert first["order_date"] == "2010-01-05" and Decimal(first["order_value"]) == Decimal("50.00")  # postage left out
    assert first["country"] == "United Kingdom" and first["channel"] == "Online retail"
    assert Decimal(orders["PUB-100005"]["order_value"]) == Decimal("10.00")  # overlap counted once, not twice
    assert orders["PUB-100006"]["customer_id"] == "PUB-15000"                # 15000.0 -> "15000"
    assert Decimal(orders["PUB-100006"]["order_value"]) == Decimal("8.50")

    assert stats["cancellation_rows"] == 1 and stats["guest_rows"] == 1
    assert stats["non_product_rows"] == 1 and stats["non_positive_rows"] == 1
    assert stats["duplicate_rows_in_overlap"] == 1
    assert (stats["orders"], stats["customers"]) == (3, 2)


def test_rows_are_sorted_by_date_and_pass_the_real_import_validator(workbook_path):
    rows, _ = convert_module.convert(workbook_path)
    assert [r["order_date"] for r in rows] == sorted(r["order_date"] for r in rows)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    result = validate_rows(parse_file(buffer.getvalue().encode(), "csv"))
    assert result.errors == [] and len(result.rows) == 3
