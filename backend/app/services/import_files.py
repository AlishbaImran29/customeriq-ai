"""Read uploaded CSV / XLSX files into header + rows, with file-level checks.

Row numbers match what a person sees in Excel or a text editor: the header is
row 1 (or wherever it appears) and each later record keeps its own number.
"""

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import PurePath

from app.core.errors import ApiError

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_DATA_ROWS = 50_000

# A cell value as read from either format.
Cell = str | int | float | Decimal | date | datetime | None


@dataclass(frozen=True)
class SheetRow:
    number: int
    values: tuple[Cell, ...]


@dataclass(frozen=True)
class ParsedFile:
    headers: list[str]
    rows: list[SheetRow]


def file_type_of(filename: str) -> str:
    """Return "csv" or "xlsx", or raise a 415 error for anything else."""
    suffix = PurePath(filename).suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".xlsx":
        return "xlsx"
    if suffix == ".xls":
        raise ApiError(
            415,
            "unsupported_file_type",
            "Old Excel .xls files are not supported. In Excel choose "
            "File → Save As → Excel Workbook (.xlsx), or export as CSV.",
        )
    raise ApiError(
        415,
        "unsupported_file_type",
        "Only .csv and .xlsx files can be imported.",
    )


def parse_file(content: bytes, file_type: str) -> ParsedFile:
    if not content.strip():
        raise ApiError(400, "empty_file", "The file is empty.")
    # Readers return only non-empty rows; the first one is the header.
    table = _read_csv(content) if file_type == "csv" else _read_xlsx(content)
    if not table:
        raise ApiError(400, "empty_file", "The file has no header row or data.")

    header_row, rows = table[0], table[1:]
    headers = [str(v).strip() if v is not None else "" for v in header_row.values]
    if not rows:
        raise ApiError(400, "no_data_rows", "The file has a header row but no data rows.")
    if len(rows) > MAX_DATA_ROWS:
        raise ApiError(
            413,
            "too_many_rows",
            f"The file has {len(rows):,} data rows; the limit is {MAX_DATA_ROWS:,}. "
            "Split it into smaller files.",
        )
    return ParsedFile(headers=headers, rows=rows)


def _has_value(value: Cell) -> bool:
    return value is not None and str(value).strip() != ""


def _is_blank(values: tuple[Cell, ...]) -> bool:
    return not any(_has_value(v) for v in values)


# Stop reading once the limit is clearly exceeded (header + MAX + 1 rows).
_READ_LIMIT = MAX_DATA_ROWS + 2


def _decode_text(content: bytes) -> str:
    if b"\x00" in content[:4096]:
        raise ApiError(
            400, "unreadable_file", "The file does not look like a text CSV file."
        )
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Excel on Windows often saves CSV as Windows-1252 ("ANSI").
        return content.decode("cp1252", errors="replace")


def _read_csv(content: bytes) -> list[SheetRow]:
    text = _decode_text(content)
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        table: list[SheetRow] = []
        # Numbered by record, which is the row number Excel shows for a CSV.
        for number, record in enumerate(reader, 1):
            if _is_blank(tuple(record)):
                continue
            table.append(SheetRow(number=number, values=tuple(record)))
            if len(table) >= _READ_LIMIT:
                break
        return table
    except csv.Error as exc:
        raise ApiError(
            400,
            "malformed_csv",
            f"The CSV could not be read near line {reader.line_num}: {exc}.",
        ) from exc


def _read_xlsx(content: bytes) -> list[SheetRow]:
    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise ApiError(
            400,
            "unreadable_file",
            "The file is not a valid .xlsx workbook. It may be damaged or be a "
            "different format renamed to .xlsx.",
        )
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ApiError(
            400, "unreadable_file", "The .xlsx workbook could not be opened."
        ) from exc
    try:
        sheet = workbook.worksheets[0] if workbook.worksheets else None
        if sheet is None:
            raise ApiError(400, "empty_file", "The workbook has no sheets.")
        table: list[SheetRow] = []
        for number, values in enumerate(sheet.iter_rows(min_row=1, values_only=True), 1):
            if _is_blank(tuple(values)):
                continue
            table.append(SheetRow(number=number, values=tuple(values)))
            if len(table) >= _READ_LIMIT:
                break
        return table
    finally:
        workbook.close()
