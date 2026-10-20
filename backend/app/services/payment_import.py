"""Import the payments couriers made to the seller (CSV or Excel), and add one by hand.

Columns (header names are not case sensitive):
    courier_name   required; written any way ("TCS", "t.c.s"): see names.py
    payment_date   required; the day the money arrived (not in the future)
    amount         required; more than 0, in rupees
    reference      optional; cheque or transfer number
    order_ids      optional; the orders this payment was for, separated by commas or semicolons
    data_source    optional; marks demo data ("demo (synthetic)")

A valid row is saved, or updated when the same row was imported before (so a sheet can be uploaded
again as it grows). Invalid rows are rejected and listed; messages never repeat what was typed.
Which parcels a payment covers is NOT decided here: see cash_matching.py.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import CourierPayment
from app.services.import_files import Cell, parse_file
from app.services.import_validation import RowError, _as_text, _parse_date, _to_decimal, normalise_header
from app.services.names import Name, normalise_courier

REQUIRED_COLUMNS = ("courier_name", "payment_date", "amount")
KNOWN_COLUMNS = REQUIRED_COLUMNS + ("reference", "order_ids", "data_source")
HEADER_ALIASES = {
    "courier": "courier_name", "courier_company": "courier_name",
    "date": "payment_date", "paid_on": "payment_date", "received_on": "payment_date", "received_date": "payment_date",
    "payment_amount": "amount", "paid": "amount", "amount_paid": "amount",
    "ref": "reference", "cheque_no": "reference", "transfer_no": "reference", "transaction_id": "reference",
    "orders": "order_ids", "order_id": "order_ids", "order_numbers": "order_ids",
}
MAX_MONEY = Decimal("9999999.99")
MAX_REFERENCE = 100
MAX_ORDER_REFS = 2000
MAX_STORED_ERRORS = 200
DATA_SOURCE = "import"


@dataclass(frozen=True)
class PaymentRow:
    row: int
    courier: Name
    payment_date: date
    amount: Decimal
    reference: str | None
    order_refs: str | None          # "A1,A2": tidied, comma separated
    data_source: str | None
    external_id: str = ""


@dataclass
class PaymentValidation:
    rows: list[PaymentRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    rejected: int = 0


@dataclass
class PaymentImportResult:
    rows_in_file: int = 0
    created: int = 0
    updated: int = 0
    rejected: int = 0
    new_courier_names: list[str] = field(default_factory=list)
    error_count: int = 0
    errors: list[dict] = field(default_factory=list)


def split_order_refs(text: str | None) -> list[str]:
    return [part.strip() for part in re.split(r"[,;\n]", text or "") if part.strip()]


def _fingerprint(courier: str, paid: date, amount: Decimal, reference: str | None, refs: str | None, seen: dict[str, int]) -> str:
    """The same row always gets the same id (rows that are exactly alike get 2, 3...)."""
    base = "PAY-" + hashlib.sha256(f"{courier}|{paid.isoformat()}|{amount}|{reference or ''}|{refs or ''}".encode()).hexdigest()[:14].upper()
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}-{seen[base]}"


def _positions(headers: list[str]) -> dict[str, int]:
    positions: dict[str, int] = {}
    for index, raw in enumerate(headers):
        name = normalise_header(raw)
        name = HEADER_ALIASES.get(name, name)
        if name in KNOWN_COLUMNS and name not in positions:
            positions[name] = index
    missing = [c for c in REQUIRED_COLUMNS if c not in positions]
    if missing:
        raise ApiError(
            422, "missing_columns", f"Required column(s) missing: {', '.join(missing)}.",
            {"missingColumns": missing, "requiredColumns": list(REQUIRED_COLUMNS)},
        )
    return positions


def check_payment(
    n: int, courier_text: str | None, paid: Cell, amount: Cell, reference: str | None, order_ids: str | None,
    data_source: str | None, seen: dict[str, int], errors: list[RowError],
) -> PaymentRow | None:
    """Validate one payment; problems are appended to `errors` (and nothing is returned)."""
    courier = normalise_courier(courier_text)
    if courier is None:
        errors.append(RowError(n, "courier_name", "Value is required."))
    elif len(courier.name) > 60:
        errors.append(RowError(n, "courier_name", "Value is longer than 60 characters."))
    when = _parse_date(paid, n, [])
    if when is None:
        errors.append(RowError(n, "payment_date", "Enter a valid date (DD/MM/YYYY or YYYY-MM-DD) that is not in the future."))
    number = _to_decimal(amount.replace(",", "") if isinstance(amount, str) else amount) if _as_text(amount) is not None else None
    if number is None or not (0 < number <= MAX_MONEY):
        errors.append(RowError(n, "amount", "Must be an amount of more than 0."))
    if reference is not None and len(reference) > MAX_REFERENCE:
        errors.append(RowError(n, "reference", f"Value is longer than {MAX_REFERENCE} characters."))
    refs = ",".join(split_order_refs(order_ids)) or None
    if refs is not None and len(refs) > MAX_ORDER_REFS:
        errors.append(RowError(n, "order_ids", f"Value is longer than {MAX_ORDER_REFS} characters."))
    if data_source is not None and len(data_source) > 30:
        errors.append(RowError(n, "data_source", "Value is longer than 30 characters."))
    if errors:
        return None
    assert courier and when and number
    number = number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return PaymentRow(
        row=n, courier=courier, payment_date=when, amount=number, reference=reference, order_refs=refs,
        data_source=data_source, external_id=_fingerprint(courier.name, when, number, reference, refs, seen),
    )


def validate_payments(parsed) -> PaymentValidation:
    positions = _positions(parsed.headers)
    result = PaymentValidation()
    seen: dict[str, int] = {}
    for sheet_row in parsed.rows:
        def cell(column: str) -> Cell:
            i = positions.get(column)
            return sheet_row.values[i] if i is not None and i < len(sheet_row.values) else None

        errors: list[RowError] = []
        row = check_payment(
            sheet_row.number, _as_text(cell("courier_name")), cell("payment_date"), cell("amount"),
            _as_text(cell("reference")), _as_text(cell("order_ids")), _as_text(cell("data_source")), seen, errors,
        )
        if errors or row is None:
            result.errors.extend(errors)
            result.rejected += 1
        else:
            result.rows.append(row)
    return result


def save_payments(db: Session, rows: list[PaymentRow], default_source: str) -> tuple[int, int]:
    """Create new payments and update ones imported before. Returns (created, updated). Does not commit."""
    created = updated = 0
    existing = {
        p.external_id: p
        for start in range(0, len(rows), 1000)
        for p in db.scalars(select(CourierPayment).where(CourierPayment.external_id.in_([r.external_id for r in rows[start : start + 1000]])))
    }
    for r in rows:
        values = dict(
            courier=r.courier.name, payment_date=r.payment_date, amount=r.amount, reference=r.reference,
            order_refs=r.order_refs, source=r.data_source or default_source,
        )
        payment = existing.get(r.external_id)
        if payment is None:
            db.add(CourierPayment(external_id=r.external_id, **values))
            created += 1
        else:
            for name, value in values.items():
                setattr(payment, name, value)
            updated += 1
    return created, updated


def import_payments(db: Session, content: bytes, file_type: str, default_source: str = DATA_SOURCE) -> PaymentImportResult:
    parsed = parse_file(content, file_type)
    checked = validate_payments(parsed)
    result = PaymentImportResult(rows_in_file=len(parsed.rows), rejected=checked.rejected)
    problems = sorted(checked.errors, key=lambda e: e.row or 0)
    result.error_count = len(problems)
    result.errors = [e.as_dict() for e in problems[:MAX_STORED_ERRORS]]
    if checked.rows:
        result.created, result.updated = save_payments(db, checked.rows, default_source)
        db.commit()
    result.new_courier_names = sorted({r.courier.name for r in checked.rows if not r.courier.known})
    return result


def add_payment(
    db: Session, courier: str, paid: date, amount: Decimal, reference: str | None, order_ids: str | None
) -> PaymentRow:
    """One payment typed in by hand. Raises ApiError (422) naming the field that is wrong."""
    errors: list[RowError] = []
    row = check_payment(1, courier, paid, amount, reference or None, order_ids or None, None, {}, errors)
    if row is None:
        first = errors[0]
        raise ApiError(422, "invalid_payment", f"{first.column}: {first.message}", {"column": first.column})
    # A hand-typed payment is its own record: typing the same one twice is allowed, and counts twice.
    count = len(list(db.scalars(select(CourierPayment.id).where(CourierPayment.external_id.like(row.external_id + "%")))))
    external_id = row.external_id if count == 0 else f"{row.external_id}-{count + 1}"
    db.add(CourierPayment(
        external_id=external_id, courier=row.courier.name, payment_date=row.payment_date, amount=row.amount,
        reference=row.reference, order_refs=row.order_refs, source="manual",
    ))
    db.commit()
    return row
