"""Import units sold per product (CSV or Excel) and load them for the Season Forecast.

Columns (header names are not case sensitive):
    product    required; the product name (spaces tidied, at most 120 characters)
    data_source optional; marks demo data ("demo (synthetic)") or a public dataset
    date       required; any day of the sale or the week (not in the future). Aliases: week_start, sale_date
    units      required; a whole number of 0 or more. Aliases: quantity, qty

Rows are added up per product per week (weeks start on Monday), so a daily sheet or a weekly sheet both
work. Uploading again REPLACES the saved total for each product-week in the file, so a sheet can be sent
again as it grows. Send the whole history of a week in one file. Invalid rows are rejected and listed;
messages never repeat what was typed.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import ProductSale
from app.models.shipment import SOURCE_DEMO
from app.services.import_files import Cell, parse_file
from app.services.import_validation import RowError, _as_text, _parse_date, _to_decimal, normalise_header
from app.services.season_forecast import WeeklySales, week_of

REQUIRED_COLUMNS = ("product", "date", "units")
HEADER_ALIASES = {
    "product_name": "product", "item": "product", "description": "product", "name": "product",
    "week_start": "date", "sale_date": "date", "week": "date", "order_date": "date",
    "quantity": "units", "qty": "units", "units_sold": "units",
}
MAX_PRODUCT = 120
MAX_UNITS = 10_000_000
MAX_STORED_ERRORS = 200
DATA_SOURCE = "import"


@dataclass
class ProductSalesImportResult:
    rows_in_file: int = 0
    weeks_created: int = 0
    weeks_updated: int = 0
    rejected: int = 0
    products: int = 0
    first_week: date | None = None
    last_week: date | None = None
    error_count: int = 0
    errors: list[dict] = field(default_factory=list)


def tidy_product(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _positions(headers: list[str]) -> dict[str, int]:
    positions: dict[str, int] = {}
    for index, raw in enumerate(headers):
        name = normalise_header(raw)
        name = HEADER_ALIASES.get(name, name)
        if name in REQUIRED_COLUMNS + ("data_source",) and name not in positions:
            positions[name] = index
    missing = [c for c in REQUIRED_COLUMNS if c not in positions]
    if missing:
        raise ApiError(
            422, "missing_columns", f"Required column(s) missing: {', '.join(missing)}.",
            {"missingColumns": missing, "requiredColumns": list(REQUIRED_COLUMNS)},
        )
    return positions


def import_product_sales(db: Session, content: bytes, file_type: str, default_source: str = DATA_SOURCE) -> ProductSalesImportResult:
    parsed = parse_file(content, file_type)
    positions = _positions(parsed.headers)
    result = ProductSalesImportResult(rows_in_file=len(parsed.rows))
    totals: dict[tuple[str, date], int] = defaultdict(int)
    sources: dict[tuple[str, date], str] = {}
    errors: list[RowError] = []
    for sheet_row in parsed.rows:
        n = sheet_row.number

        def cell(column: str) -> Cell:
            i = positions.get(column)
            return sheet_row.values[i] if i is not None and i < len(sheet_row.values) else None

        found: list[RowError] = []
        raw_name = _as_text(cell("product"))
        product = tidy_product(raw_name) if raw_name else ""
        if not product:
            found.append(RowError(n, "product", "Value is required."))
        elif len(product) > MAX_PRODUCT:
            found.append(RowError(n, "product", f"Value is longer than {MAX_PRODUCT} characters."))
        day = _parse_date(cell("date"), n, [])
        if day is None:
            found.append(RowError(n, "date", "Enter a valid date (DD/MM/YYYY or YYYY-MM-DD) that is not in the future."))
        number = _to_decimal(cell("units").replace(",", "") if isinstance(cell("units"), str) else cell("units")) if _as_text(cell("units")) is not None else None
        if number is None or number < 0 or number != number.to_integral_value() or number > MAX_UNITS:
            found.append(RowError(n, "units", "Must be a whole number of 0 or more."))
        marker = _as_text(cell("data_source"))
        if marker is not None and len(marker) > 30:
            found.append(RowError(n, "data_source", "Value is longer than 30 characters."))
        if found:
            errors.extend(found)
            result.rejected += 1
            continue
        key = (product, week_of(day))
        totals[key] += int(number)
        sources[key] = marker or default_source
    problems = sorted(errors, key=lambda e: e.row or 0)
    result.error_count = len(problems)
    result.errors = [e.as_dict() for e in problems[:MAX_STORED_ERRORS]]
    if totals:
        products = sorted({p for p, _ in totals})
        existing = {
            (row.product, row.week_start): row
            for start in range(0, len(products), 500)
            for row in db.scalars(select(ProductSale).where(ProductSale.product.in_(products[start : start + 500])))
        }
        for (product, week), units in totals.items():
            row = existing.get((product, week))
            if row is None:
                db.add(ProductSale(product=product, week_start=week, units=units, source=sources[(product, week)]))
                result.weeks_created += 1
            else:
                row.units, row.source = units, sources[(product, week)]
                result.weeks_updated += 1
        db.commit()
        result.products = len(products)
        result.first_week = min(w for _, w in totals)
        result.last_week = max(w for _, w in totals)
    return result


def load_weekly_sales(db: Session, source: str = "auto") -> tuple[str, int, int, WeeklySales]:
    """(source used, real product-weeks, demo product-weeks, sales). Real data is used when there is any;
    demo (made-up) data only when there is nothing else."""
    from sqlalchemy import func

    real = db.scalar(select(func.count()).select_from(ProductSale).where(ProductSale.source.is_distinct_from(SOURCE_DEMO))) or 0
    demo = db.scalar(select(func.count()).select_from(ProductSale).where(ProductSale.source == SOURCE_DEMO)) or 0
    used = source if source in ("real", "demo") else ("real" if real else "demo" if demo else "real")
    condition = ProductSale.source == SOURCE_DEMO if used == "demo" else ProductSale.source.is_distinct_from(SOURCE_DEMO)
    series: dict[str, dict[date, int]] = defaultdict(dict)
    for product, week, units in db.execute(select(ProductSale.product, ProductSale.week_start, ProductSale.units).where(condition)):
        series[product][week] = units
    return used, int(real), int(demo), WeeklySales(dict(series))
