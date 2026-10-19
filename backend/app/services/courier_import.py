"""Import a courier status file: the real "delivered / returned" result of each parcel.

Columns: order_id, customer_id, status, date. For every row the matching order gets
`outcome`, `outcome_date` (the day the status became known) and `label_source = courier data`.
This REAL label replaces a proxy label (an order cancelled in the shop's own files) for that
order, so the Order Risk model learns from what really happened.

Rules:
- The order must already exist, and customer_id must be the customer of that order
  (a mix-up here would give the wrong customer a bad history, so it is rejected).
- Valid rows are saved; invalid rows are rejected and listed (messages never repeat values).
- `status` accepts delivered, or returned (also return, rto, refused: a courier "return to
  origin" or a refused parcel both mean the parcel came back).
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import Customer, Order
from app.models.order import LABEL_COURIER, OUTCOME_DELIVERED, OUTCOME_RETURNED
from app.services.import_files import ParsedFile, parse_file
from app.services.import_validation import RowError, _as_text, _parse_date, normalise_header

REQUIRED = ("order_id", "customer_id", "status", "date")
MAX_STORED_ERRORS = 200
_STATUS = {
    "delivered": OUTCOME_DELIVERED,
    "returned": OUTCOME_RETURNED,
    "return": OUTCOME_RETURNED,
    "rto": OUTCOME_RETURNED,
    "refused": OUTCOME_RETURNED,
}
_LOOKUP_BATCH = 1000


@dataclass
class CourierResult:
    rows_in_file: int = 0
    rows_updated: int = 0
    rows_returned: int = 0
    rows_rejected: int = 0
    error_count: int = 0
    errors: list[dict] = field(default_factory=list)


def run_courier_import(db: Session, content: bytes, file_type: str) -> CourierResult:
    parsed = parse_file(content, file_type)
    positions = _positions(parsed)
    result = CourierResult(rows_in_file=len(parsed.rows))
    problems: list[RowError] = []

    # Read every row first. An order_id may appear once per file (the first row counts, like in the
    # orders import), so every row ends up either saved or rejected.
    wanted: dict[str, tuple[int, str, str, object]] = {}  # order_id -> (row, customer_id, outcome, date)
    for sheet_row in parsed.rows:
        n = sheet_row.number

        def cell(column: str):
            i = positions[column]
            return sheet_row.values[i] if i < len(sheet_row.values) else None

        order_id, customer_id = _as_text(cell("order_id")), _as_text(cell("customer_id"))
        status = (_as_text(cell("status")) or "").lower()
        row_problems: list[RowError] = []
        if order_id is None:
            row_problems.append(RowError(n, "order_id", "Value is required."))
        if customer_id is None:
            row_problems.append(RowError(n, "customer_id", "Value is required."))
        if status not in _STATUS:
            row_problems.append(RowError(n, "status", "Must be delivered or returned."))
        found: list[RowError] = []
        day = _parse_date(cell("date"), n, found)
        row_problems.extend(RowError(e.row, "date", e.message) for e in found)
        if not row_problems and order_id in wanted:
            row_problems.append(
                RowError(n, "order_id", f"Duplicate order_id in this file (first used on row {wanted[order_id][0]}).")
            )
        if row_problems:
            problems.extend(row_problems)
            result.rows_rejected += 1
            continue
        wanted[order_id] = (n, customer_id, _STATUS[status], day)

    # Look the orders up in batches, with the customer's own id for the match check.
    ids = list(wanted)
    for start in range(0, len(ids), _LOOKUP_BATCH):
        batch = ids[start : start + _LOOKUP_BATCH]
        rows = db.execute(
            select(Order, Customer.external_id)
            .join(Customer, Customer.id == Order.customer_id)
            .where(Order.external_id.in_(batch))
        )
        found_orders = {order.external_id: (order, customer) for order, customer in rows}
        for order_id in batch:
            n, customer_id, outcome, day = wanted[order_id]
            if order_id not in found_orders:
                problems.append(RowError(n, "order_id", "No order with this id has been imported."))
                result.rows_rejected += 1
                continue
            order, owner = found_orders[order_id]
            if owner != customer_id:
                problems.append(RowError(n, "customer_id", "This order belongs to a different customer."))
                result.rows_rejected += 1
            elif day < order.order_date:
                problems.append(RowError(n, "date", "Cannot be before the order date."))
                result.rows_rejected += 1
            else:
                order.outcome = outcome
                order.outcome_date = day
                order.label_source = LABEL_COURIER
                result.rows_updated += 1
                result.rows_returned += outcome == OUTCOME_RETURNED
    db.commit()

    problems.sort(key=lambda e: e.row or 0)
    result.error_count = len(problems)
    result.errors = [e.as_dict() for e in problems[:MAX_STORED_ERRORS]]
    return result


def _positions(parsed: ParsedFile) -> dict[str, int]:
    names = {}
    for index, header in enumerate(parsed.headers):
        names.setdefault(normalise_header(header), index)
    missing = [c for c in REQUIRED if c not in names]
    if missing:
        raise ApiError(
            422,
            "missing_columns",
            f"Required column(s) missing: {', '.join(missing)}.",
            {"missingColumns": missing, "requiredColumns": list(REQUIRED)},
        )
    return {c: names[c] for c in REQUIRED}
