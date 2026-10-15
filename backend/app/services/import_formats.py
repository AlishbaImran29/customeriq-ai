"""Recognise store-export formats and convert them to the standard import columns.

Supported: the standard CustomerIQ columns, and the Shopify orders export
(Admin → Orders → Export). Column reference:
https://help.shopify.com/en/manual/fulfillment/managing-orders/exporting-orders

Shopify specifics handled here:
- One row per line item; extra rows of an order leave many fields blank, so
  order-level values are taken from the first row of that order that has them.
- There is no customer ID column, so the (lower-cased) Email identifies the customer.
- Canceled, voided and fully refunded orders are skipped and reported.
- Partially refunded orders count Total minus Refunded Amount.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.services.import_files import Cell, ParsedFile, SheetRow
from app.services.import_validation import (
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    RowError,
    normalise_header,
)

FileFormat = Literal["standard", "shopify"]

_SHOPIFY_MARKERS = {"name", "email", "created_at", "total", "financial_status"}
_SKIP_STATUSES = {"voided": "voided", "refunded": "fully refunded"}
_STANDARD = REQUIRED_COLUMNS + OPTIONAL_COLUMNS


@dataclass
class Converted:
    parsed: ParsedFile
    file_format: FileFormat
    # Orders skipped on purpose (e.g. canceled), reported like row problems.
    skipped: list[RowError]


def detect_format(headers: list[str]) -> FileFormat:
    names = {normalise_header(h) for h in headers}
    if "order_id" not in names and _SHOPIFY_MARKERS <= names:
        return "shopify"
    return "standard"


def convert(parsed: ParsedFile) -> Converted:
    if detect_format(parsed.headers) == "shopify":
        return _convert_shopify(parsed)
    return Converted(parsed=parsed, file_format="standard", skipped=[])


def _text(value: Cell) -> str:
    return "" if value is None else str(value).strip()


def _decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", "")) if value else None
    except InvalidOperation:
        return None


def _convert_shopify(parsed: ParsedFile) -> Converted:
    index: dict[str, int] = {}
    for i, header in enumerate(parsed.headers):
        index.setdefault(normalise_header(header), i)  # "Phone" appears twice; keep the first

    def cell(row: SheetRow, column: str) -> str:
        i = index.get(column)
        return _text(row.values[i]) if i is not None and i < len(row.values) else ""

    # Group line-item rows by order number, keeping file order.
    orders: dict[str, list[SheetRow]] = {}
    for row in parsed.rows:
        orders.setdefault(cell(row, "name"), []).append(row)

    rows: list[SheetRow] = []
    skipped: list[RowError] = []
    for order_name, items in orders.items():
        first_row = items[0].number

        def first(column: str) -> str:
            return next((v for v in (cell(r, column) for r in items) if v), "")

        if not order_name:
            # Rows without an order number cannot be grouped; let validation report them.
            for r in items:
                rows.append(SheetRow(r.number, _standard_values({"email": cell(r, "email")})))
            continue
        if first("canceled_at") or first("cancelled_at"):
            skipped.append(RowError(first_row, "Canceled at", "Skipped: the order was canceled."))
            continue
        status = first("financial_status").lower()
        if status in _SKIP_STATUSES:
            skipped.append(
                RowError(first_row, "Financial Status", f"Skipped: the order was {_SKIP_STATUSES[status]}.")
            )
            continue

        total = first("total")
        refunded = _decimal(first("refunded_amount"))
        value = total
        if refunded and _decimal(total) is not None:
            value = str(max(Decimal(0), _decimal(total) - refunded))

        billing_name = first("billing_name")
        first_name, _, last_name = billing_name.partition(" ")
        source = first("source")
        email = first("email").lower()
        rows.append(
            SheetRow(
                first_row,
                _standard_values(
                    {
                        "customer_id": email,
                        "email": email,
                        "order_id": order_name,
                        "order_date": first("created_at"),
                        "order_value": value,
                        "first_name": first_name,
                        "last_name": last_name,
                        "country": first("billing_country") or first("shipping_country"),
                        "channel": f"Shopify ({source})" if source else "Shopify",
                    }
                ),
            )
        )

    return Converted(
        parsed=ParsedFile(headers=list(_STANDARD), rows=rows),
        file_format="shopify",
        skipped=skipped,
    )


def _standard_values(values: dict[str, str]) -> tuple[Cell, ...]:
    return tuple(values.get(column) or None for column in _STANDARD)
