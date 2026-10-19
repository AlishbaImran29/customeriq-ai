"""File reading and row validation. No database needed."""

import io
from datetime import date, datetime
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.core.errors import ApiError
from app.services.import_files import MAX_DATA_ROWS, file_type_of, parse_file
from app.services.import_validation import validate_rows

HEADER = "customer_id,email,order_id,order_date,order_value"


def csv_bytes(*lines: str, encoding: str = "utf-8") -> bytes:
    return "\n".join(lines).encode(encoding)


def xlsx_bytes(rows: list[list]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def error_code(exc_info) -> str:
    return exc_info.value.code


# --- file type --------------------------------------------------------------

@pytest.mark.parametrize("name, expected", [("a.csv", "csv"), ("B.XLSX", "xlsx")])
def test_file_type_accepts_csv_and_xlsx(name, expected):
    assert file_type_of(name) == expected


def test_file_type_rejects_xls_with_save_as_hint():
    with pytest.raises(ApiError) as exc:
        file_type_of("old.xls")
    assert exc.value.status_code == 415 and ".xlsx" in exc.value.message


def test_file_type_rejects_other_extensions():
    with pytest.raises(ApiError) as exc:
        file_type_of("notes.txt")
    assert exc.value.status_code == 415


# --- file-level problems ----------------------------------------------------

def test_empty_file_rejected():
    with pytest.raises(ApiError) as exc:
        parse_file(b"  \n\n", "csv")
    assert error_code(exc) == "empty_file"


def test_header_only_rejected():
    with pytest.raises(ApiError) as exc:
        parse_file(csv_bytes(HEADER), "csv")
    assert error_code(exc) == "no_data_rows"


def test_binary_data_in_csv_rejected():
    with pytest.raises(ApiError) as exc:
        parse_file(b"\x00\x01\x02garbage", "csv")
    assert error_code(exc) == "unreadable_file"


def test_fake_xlsx_rejected():
    with pytest.raises(ApiError) as exc:
        parse_file(b"this is not a zip file", "xlsx")
    assert error_code(exc) == "unreadable_file"


def test_missing_required_columns_lists_them():
    parsed = parse_file(csv_bytes("customer_id,email", "C1,a@example.com"), "csv")
    with pytest.raises(ApiError) as exc:
        validate_rows(parsed)
    assert exc.value.status_code == 422
    assert exc.value.details["missingColumns"] == ["order_date", "order_value"]   # the order number is optional now


def test_duplicate_column_rejected():
    parsed = parse_file(csv_bytes(HEADER + ",Email", "C1,a@example.com,O1,2026-01-01,5,x"), "csv")
    with pytest.raises(ApiError) as exc:
        validate_rows(parsed)
    assert error_code(exc) == "duplicate_columns"


def test_too_many_rows_rejected():
    lines = [HEADER] + [f"C{i},c{i}@example.com,O{i},2026-01-01,1" for i in range(MAX_DATA_ROWS + 1)]
    with pytest.raises(ApiError) as exc:
        parse_file(csv_bytes(*lines), "csv")
    assert error_code(exc) == "too_many_rows"


def test_blank_lines_do_not_count_toward_row_limit():
    lines = [HEADER] + [""] * 100 + ["C1,a@example.com,O1,2026-01-01,1"]
    assert len(parse_file(csv_bytes(*lines), "csv").rows) == 1


# --- headers and encoding ---------------------------------------------------

def test_headers_are_case_and_space_insensitive():
    parsed = parse_file(
        csv_bytes("Customer ID,EMAIL,Order-ID,order date,Order_Value", "C1,a@example.com,O1,2026-01-01,9.5"),
        "csv",
    )
    result = validate_rows(parsed)
    assert len(result.rows) == 1 and not result.errors


def test_utf8_bom_and_windows_1252_csv_are_read():
    for content in (
        "﻿".encode() + csv_bytes(HEADER + ",first_name", "C1,a@example.com,O1,2026-01-01,1,José"),
        csv_bytes(HEADER + ",first_name", "C1,a@example.com,O1,2026-01-01,1,José", encoding="cp1252"),
    ):
        result = validate_rows(parse_file(content, "csv"))
        assert result.rows[0].first_name == "José"


# --- row validation ---------------------------------------------------------

def test_valid_row_is_cleaned():
    parsed = parse_file(
        csv_bytes(
            HEADER + ",engagement,channel",
            " C1 , Amelia@Example.com ,O1,2026-03-04,142.505,87.5,Shopify",
        ),
        "csv",
    )
    row = validate_rows(parsed).rows[0]
    assert row.customer_id == "C1"
    assert row.email == "amelia@example.com"
    assert row.order_date == date(2026, 3, 4)
    assert row.order_value == Decimal("142.51")
    assert row.engagement == Decimal("87.50")
    assert row.channel == "Shopify"


def test_blank_engagement_is_none_not_zero():
    parsed = parse_file(csv_bytes(HEADER + ",engagement", "C1,a@example.com,O1,2026-01-01,1,"), "csv")
    assert validate_rows(parsed).rows[0].engagement is None


def test_bad_rows_rejected_with_row_numbers_and_no_values():
    parsed = parse_file(
        csv_bytes(
            HEADER + ",engagement",
            "C1,good@example.com,O1,2026-01-01,10,50",       # row 2: valid
            "C2,not-an-email,O2,April 3rd,abc,150",          # row 3: four problems
            ",x@example.com,O3,2026-01-01,-5,",              # row 4: one problem (the email is enough to identify them)
            "C4,d@example.com,O1,2026-01-02,5,",             # row 5: duplicate order
        ),
        "csv",
    )
    result = validate_rows(parsed)
    assert [r.order_id for r in result.rows] == ["O1"]
    assert result.rejected_rows == 3
    problems = {(e.row, e.column) for e in result.errors}
    assert problems == {
        (3, "email"), (3, "order_date"), (3, "order_value"), (3, "engagement"),
        (4, "order_value"),
        (5, "order_id"),
    }
    text = " ".join(e.message for e in result.errors)
    for value in ("not-an-email", "April 3rd", "abc", "150", "-5"):
        assert value not in text


def test_future_date_rejected():
    parsed = parse_file(csv_bytes(HEADER, "C1,a@example.com,O1,2999-01-01,1"), "csv")
    assert validate_rows(parsed).errors[0].message == "Date is in the future."


def test_too_long_value_rejected():
    parsed = parse_file(csv_bytes(HEADER, f"{'C' * 101},a@example.com,O1,2026-01-01,1"), "csv")
    error = validate_rows(parsed).errors[0]
    assert error.column == "customer_id" and "100" in error.message


# --- xlsx -------------------------------------------------------------------

def test_xlsx_native_types_and_row_numbers():
    content = xlsx_bytes(
        [
            ["customer_id", "email", "order_id", "order_date", "order_value"],
            [1042, "a@example.com", "O1", datetime(2026, 5, 1, 9, 30), 99.9],
            [None, None, None, None, None],
            [1043, "b@example.com", "O2", "2026-05-02", "bad"],
        ]
    )
    result = validate_rows(parse_file(content, "xlsx"))
    row = result.rows[0]
    assert row.customer_id == "1042"  # not "1042.0"
    assert row.order_date == date(2026, 5, 1)
    assert row.order_value == Decimal("99.90")
    assert [(e.row, e.column) for e in result.errors] == [(4, "order_value")]
