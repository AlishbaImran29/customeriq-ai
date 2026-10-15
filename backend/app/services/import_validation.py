"""Validate imported rows. Error messages describe problems without echoing values."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.core.errors import ApiError
from app.services.import_files import Cell, ParsedFile

REQUIRED_COLUMNS = ("customer_id", "email", "order_id", "order_date", "order_value")
OPTIONAL_COLUMNS = (
    "first_name",
    "last_name",
    "country",
    "product_category",
    "channel",
    "engagement",
)
KNOWN_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

MAX_LENGTHS = {
    "customer_id": 100,
    "order_id": 100,
    "email": 320,
    "first_name": 100,
    "last_name": 100,
    "country": 100,
    "product_category": 100,
    "channel": 50,
}
MAX_ORDER_VALUE = Decimal("9999999999.99")  # fits NUMERIC(12, 2)
_CENTS = Decimal("0.01")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class RowError:
    row: int | None
    column: str | None
    message: str

    def as_dict(self) -> dict[str, int | str | None]:
        return {"row": self.row, "column": self.column, "message": self.message}


@dataclass(frozen=True)
class OrderRow:
    row: int
    customer_id: str
    email: str
    order_id: str
    order_date: date
    order_value: Decimal
    first_name: str | None
    last_name: str | None
    country: str | None
    product_category: str | None
    channel: str | None
    engagement: Decimal | None


@dataclass
class ValidationResult:
    rows: list[OrderRow]
    errors: list[RowError]
    rejected_rows: int


def normalise_header(header: str) -> str:
    return re.sub(r"[\s\-]+", "_", header.strip().lower())


def column_positions(headers: list[str]) -> dict[str, int]:
    """Map known column names to their index; raise 422 if required ones are missing."""
    positions: dict[str, int] = {}
    duplicates: list[str] = []
    for index, raw in enumerate(headers):
        name = normalise_header(raw)
        if name in KNOWN_COLUMNS:
            if name in positions:
                duplicates.append(name)
            else:
                positions[name] = index
    missing = [c for c in REQUIRED_COLUMNS if c not in positions]
    if missing:
        raise ApiError(
            422,
            "missing_columns",
            f"Required column(s) missing: {', '.join(missing)}.",
            {"missingColumns": missing, "requiredColumns": list(REQUIRED_COLUMNS)},
        )
    if duplicates:
        raise ApiError(
            422,
            "duplicate_columns",
            f"Column(s) appear more than once: {', '.join(sorted(set(duplicates)))}.",
            {"duplicateColumns": sorted(set(duplicates))},
        )
    return positions


def validate_rows(parsed: ParsedFile) -> ValidationResult:
    positions = column_positions(parsed.headers)
    valid: list[OrderRow] = []
    errors: list[RowError] = []
    rejected = 0
    first_seen_order: dict[str, int] = {}

    for sheet_row in parsed.rows:
        values = sheet_row.values

        def cell(column: str) -> Cell:
            index = positions.get(column)
            return values[index] if index is not None and index < len(values) else None

        row_errors: list[RowError] = []
        n = sheet_row.number

        def text(column: str, required: bool) -> str | None:
            value = _as_text(cell(column))
            if value is None:
                if required:
                    row_errors.append(RowError(n, column, "Value is required."))
                return None
            limit = MAX_LENGTHS.get(column)
            if limit and len(value) > limit:
                row_errors.append(
                    RowError(n, column, f"Value is longer than {limit} characters.")
                )
                return None
            return value

        customer_id = text("customer_id", required=True)
        order_id = text("order_id", required=True)
        email = text("email", required=True)
        if email is not None and not _EMAIL.match(email):
            row_errors.append(RowError(n, "email", "Not a valid email address."))
            email = None
        order_date = _parse_date(cell("order_date"), n, row_errors)
        order_value = _parse_order_value(cell("order_value"), n, row_errors)
        engagement = _parse_engagement(cell("engagement"), n, row_errors)
        optional = {c: text(c, required=False) for c in OPTIONAL_COLUMNS if c != "engagement"}

        if order_id is not None:
            if order_id in first_seen_order:
                row_errors.append(
                    RowError(
                        n,
                        "order_id",
                        f"Duplicate order_id in this file (first used on row "
                        f"{first_seen_order[order_id]}).",
                    )
                )
            else:
                first_seen_order[order_id] = n

        if row_errors:
            errors.extend(row_errors)
            rejected += 1
            continue

        assert customer_id and order_id and email and order_date and order_value is not None
        valid.append(
            OrderRow(
                row=n,
                customer_id=customer_id,
                email=email.lower(),
                order_id=order_id,
                order_date=order_date,
                order_value=order_value,
                engagement=engagement,
                **optional,
            )
        )

    return ValidationResult(rows=valid, errors=errors, rejected_rows=rejected)


def _as_text(value: Cell) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        # Excel stores IDs like 1042 as 1042.0.
        value = int(value)
    text = str(value).strip()
    return text or None


def _parse_date(value: Cell, row: int, errors: list[RowError]) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _as_text(value)
    if text is None:
        errors.append(RowError(row, "order_date", "Value is required."))
        return None
    candidate = text[:10] if len(text) > 10 and text[10] in " T" else text
    if _ISO_DATE.match(candidate):
        try:
            parsed = date.fromisoformat(candidate)
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed > date.today():
                errors.append(RowError(row, "order_date", "Date is in the future."))
                return None
            return parsed
    errors.append(
        RowError(row, "order_date", "Not a valid date. Use the format YYYY-MM-DD.")
    )
    return None


def _to_decimal(value: Cell) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, Decimal)):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    text = _as_text(value)
    if text is None:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _parse_order_value(value: Cell, row: int, errors: list[RowError]) -> Decimal | None:
    if _as_text(value) is None:
        errors.append(RowError(row, "order_value", "Value is required."))
        return None
    number = _to_decimal(value)
    if number is None:
        errors.append(
            RowError(row, "order_value", "Not a number. Use digits only, e.g. 142.50.")
        )
        return None
    if number < 0:
        errors.append(RowError(row, "order_value", "Must be 0 or more."))
        return None
    number = number.quantize(_CENTS, rounding=ROUND_HALF_UP)
    if number > MAX_ORDER_VALUE:
        errors.append(RowError(row, "order_value", "Value is too large."))
        return None
    return number


def _parse_engagement(value: Cell, row: int, errors: list[RowError]) -> Decimal | None:
    if _as_text(value) is None:
        return None  # Optional: blank means "not provided", never zero.
    number = _to_decimal(value)
    if number is None or not (0 <= number <= 100):
        errors.append(
            RowError(row, "engagement", "Must be a number from 0 to 100, or left blank.")
        )
        return None
    return number.quantize(_CENTS, rounding=ROUND_HALF_UP)
