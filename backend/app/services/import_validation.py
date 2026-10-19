"""Validate imported rows. Error messages describe problems without echoing values."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.core.errors import ApiError
from app.models.order import LABEL_COURIER, LABEL_SOURCES, OUTCOME_RETURNED, OUTCOMES
from app.services.channels import normalise_channel
from app.services.phone import NOT_A_PK_MOBILE, normalise_pk_phone
from app.services.import_files import Cell, ParsedFile

REQUIRED_COLUMNS = ("order_id", "order_date", "order_value")
# A row must say WHO ordered, and any one of these is enough: a customer id, an email, or a
# phone number (sellers on WhatsApp or Instagram often have only a phone number).
IDENTITY_COLUMNS = ("customer_id", "email", "phone")
IDENTITY_LABEL = "customer_id or email or phone (at least one)"
OPTIONAL_COLUMNS = (
    "first_name",
    "last_name",
    "country",
    "product_category",
    "channel",
    "engagement",
)
# Optional columns for the Order Risk Check. Blank means "not provided", never zero.
RISK_COLUMNS = (
    "order_datetime",     # YYYY-MM-DD HH:MM[:SS]: the time of day; order_date is still the day
    "item_count",
    "distinct_products",
    "outcome",            # delivered | returned
    "outcome_date",       # the day the outcome became known (required for "returned")
    "label_source",       # "proxy: cancellations" | "courier data" (default: courier data)
    "phone",
    "address",            # only used for simple checks; the text itself is not stored
)
KNOWN_COLUMNS = REQUIRED_COLUMNS + ("customer_id", "email") + OPTIONAL_COLUMNS + RISK_COLUMNS

MAX_LENGTHS = {
    "customer_id": 100,
    "order_id": 100,
    "email": 320,
    "first_name": 100,
    "last_name": 100,
    "country": 100,
    "product_category": 100,
    "channel": 50,
    "phone": 40,
}
MAX_ADDRESS_LENGTH = 1000
MAX_ITEMS = 100_000
MAX_ORDER_VALUE = Decimal("9999999999.99")  # fits NUMERIC(12, 2)
_CENTS = Decimal("0.01")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$")


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
    customer_id: str                 # the customer's own id, or the normalised phone, or the email
    email: str | None
    order_id: str
    order_date: date
    order_value: Decimal
    first_name: str | None
    last_name: str | None
    country: str | None
    product_category: str | None
    channel: str | None
    engagement: Decimal | None
    # Order Risk Check facts (all optional).
    ordered_at: datetime | None = None
    item_count: int | None = None
    distinct_products: int | None = None
    outcome: str | None = None
    outcome_date: date | None = None
    label_source: str | None = None
    phone: str | None = None
    phone_valid: bool | None = None
    address_length: int | None = None
    has_house_number: bool | None = None
    # Social Seller Mode: the phone as +923XXXXXXXXX (None when absent or not a Pakistani mobile),
    # and the clean channel (None when the file had no channel text).
    phone_normalised: str | None = None
    sales_channel: str | None = None


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
    if not any(c in positions for c in IDENTITY_COLUMNS):
        missing.append(IDENTITY_LABEL)
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

        customer_id = text("customer_id", required=False)
        order_id = text("order_id", required=True)
        email = text("email", required=False)
        if email is not None and not _EMAIL.match(email):
            row_errors.append(RowError(n, "email", "Not a valid email address."))
            email = None
        order_date = _parse_date(cell("order_date"), n, row_errors)
        order_value = _parse_order_value(cell("order_value"), n, row_errors)
        engagement = _parse_engagement(cell("engagement"), n, row_errors)
        optional = {c: text(c, required=False) for c in OPTIONAL_COLUMNS if c != "engagement"}
        risk = _parse_risk_columns(cell, text, order_date, n, row_errors)
        phone_normalised = normalise_pk_phone(risk["phone"])
        channel_text = optional.get("channel")
        # Who ordered: the customer's own id, else their phone number, else their email.
        identity = customer_id or phone_normalised or (email.lower() if email else None)
        if identity is None and not row_errors:
            if risk["phone"]:
                row_errors.append(RowError(n, "phone", NOT_A_PK_MOBILE))
            else:
                row_errors.append(RowError(n, "customer_id", "Needs a customer_id, an email or a phone number."))

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

        assert identity and order_id and order_date and order_value is not None
        valid.append(
            OrderRow(
                row=n,
                customer_id=identity,
                email=email.lower() if email else None,
                order_id=order_id,
                order_date=order_date,
                order_value=order_value,
                engagement=engagement,
                **optional,
                **risk,
                phone_normalised=phone_normalised,
                sales_channel=normalise_channel(channel_text) if channel_text else None,
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


# --- Order Risk Check columns ---------------------------------------------------------

def _parse_risk_columns(cell, text, order_date: date | None, row: int, errors: list[RowError]) -> dict:
    """Read the optional Order Risk columns of one row. Problems are added to `errors`;
    messages never copy the value (it may be a phone number or an address)."""
    ordered_at = _parse_order_datetime(cell("order_datetime"), order_date, row, errors)
    item_count = _parse_count(cell("item_count"), "item_count", row, errors)
    distinct = _parse_count(cell("distinct_products"), "distinct_products", row, errors)
    if item_count is not None and distinct is not None and distinct > item_count:
        errors.append(RowError(row, "distinct_products", "Cannot be more than item_count."))

    outcome = _as_text(cell("outcome"))
    outcome = outcome.lower() if outcome else None
    if outcome is not None and outcome not in OUTCOMES:
        errors.append(RowError(row, "outcome", "Must be delivered or returned, or left blank."))
        outcome = None
    outcome_date = None
    has_outcome_date = _as_text(cell("outcome_date")) is not None
    if has_outcome_date:
        found: list[RowError] = []
        outcome_date = _parse_date(cell("outcome_date"), row, found)
        errors.extend(RowError(e.row, "outcome_date", e.message) for e in found)
    if outcome == OUTCOME_RETURNED and not has_outcome_date:
        # The date matters: a model may only use an outcome from after it became known.
        errors.append(RowError(row, "outcome_date", "Required when outcome is returned."))
    if outcome_date is not None and order_date is not None and outcome_date < order_date:
        errors.append(RowError(row, "outcome_date", "Cannot be before order_date."))
    if has_outcome_date and _as_text(cell("outcome")) is None:
        errors.append(RowError(row, "outcome", "Required when outcome_date is given."))

    label_source = _as_text(cell("label_source"))
    if label_source is not None and label_source not in LABEL_SOURCES:
        errors.append(
            RowError(row, "label_source", "Must be 'proxy: cancellations' or 'courier data', or left blank.")
        )
        label_source = None
    if outcome is not None and label_source is None:
        label_source = LABEL_COURIER  # an outcome typed into a file is the seller's own data

    phone = text("phone", required=False)
    address = _as_text(cell("address"))
    if address is not None and len(address) > MAX_ADDRESS_LENGTH:
        errors.append(RowError(row, "address", f"Value is longer than {MAX_ADDRESS_LENGTH} characters."))
        address = None
    return {
        "ordered_at": ordered_at,
        "item_count": item_count,
        "distinct_products": distinct,
        "outcome": outcome,
        "outcome_date": outcome_date,
        "label_source": label_source,
        "phone": phone,
        "phone_valid": None if phone is None else is_valid_phone(phone),
        "address_length": None if address is None else len(address),
        "has_house_number": None if address is None else has_house_number(address),
    }


def _parse_order_datetime(
    value: Cell, order_date: date | None, row: int, errors: list[RowError]
) -> datetime | None:
    if _as_text(value) is None:
        return None
    message = "Not a valid date and time. Use YYYY-MM-DD HH:MM."
    if isinstance(value, datetime):
        moment = value
    else:
        written = _as_text(value) or ""
        if not _ISO_DATETIME.match(written):
            errors.append(RowError(row, "order_datetime", message))
            return None
        try:
            moment = datetime.fromisoformat(written.replace(" ", "T"))
        except ValueError:
            errors.append(RowError(row, "order_datetime", message))
            return None
    if moment.tzinfo is not None:
        moment = moment.replace(tzinfo=None)  # times are stored as written, with no time zone
    if moment > datetime.now():
        errors.append(RowError(row, "order_datetime", "Time is in the future."))
        return None
    if order_date is not None and moment.date() != order_date:
        errors.append(RowError(row, "order_datetime", "Must be on the same day as order_date."))
        return None
    return moment


def _parse_count(value: Cell, column: str, row: int, errors: list[RowError]) -> int | None:
    if _as_text(value) is None:
        return None
    number = _to_decimal(value)
    if number is None or number != number.to_integral_value() or not (1 <= number <= MAX_ITEMS):
        errors.append(RowError(row, column, f"Must be a whole number from 1 to {MAX_ITEMS}, or left blank."))
        return None
    return int(number)


_PHONE_SEPARATORS = re.compile(r"[\s\-().]")
_PHONE = re.compile(r"^\+?\d{10,15}$")


def is_valid_phone(phone: str) -> bool:
    """A simple format check: 10-15 digits, an optional leading +, spaces and dashes ignored.
    It accepts Pakistani numbers such as 0300 1234567 and +92 300 1234567. It does not check
    that the number really exists."""
    return bool(_PHONE.match(_PHONE_SEPARATORS.sub("", phone)))


def has_house_number(address: str) -> bool:
    """A simple check: the address contains at least one digit (house, flat or plot number)."""
    return any(ch.isdigit() for ch in address)
