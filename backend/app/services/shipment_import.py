"""Import the parcels a seller handed to couriers (CSV or Excel).

Columns (header names are not case sensitive; common other names are understood):
    order_id, customer_id, phone      who it is for (any one helps to link it to an order; none is fine)
    courier_name                      required; written any way ("TCS", "t.c.s"): see names.py
    city                              where it goes; also tidied to one spelling
    booked_date                       required; the day it was handed to the courier
    delivered_or_returned_date        the day it was delivered or came back (needed for those two statuses)
    status                            required: delivered / returned / in_transit / lost (and words like RTO, refused)
    return_reason                     optional free text
    cod_amount, courier_fee           optional money
    data_source                       optional; marks demo data (see models/shipment.py)

What happens to a valid row:
1. It is linked to an order where that is certain: by order_id, else by customer (id or phone) and a
   booking date within 3 days of the order (and the same amount when both have one). When more than
   one order fits, it is NOT linked: a wrong link is worse than none. An unlinked shipment is still saved.
2. It is saved, or updated when the same shipment was imported before (so a sheet can be uploaded
   again as it grows).
3. If it is linked to an order and is delivered or returned, the order gets that result and its date
   (label source "courier data"), which is the real answer the Order Risk model learns from.

Invalid rows are rejected and listed; error messages never repeat what was typed.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import Customer, Order, Shipment
from app.models.order import LABEL_COURIER
from app.models.shipment import CLOSED_STATUSES, SOURCE_DEMO, STATUS_DELIVERED, STATUS_IN_TRANSIT, STATUS_LOST, STATUS_RETURNED
from app.services.import_files import Cell, ParsedFile, parse_file
from app.services.import_validation import RowError, _as_text, _parse_date, _to_decimal, normalise_header
from app.services.names import Name, normalise_city, normalise_courier
from app.services.phone import normalise_pk_phone

REQUIRED_COLUMNS = ("courier_name", "booked_date", "status")
KNOWN_COLUMNS = REQUIRED_COLUMNS + (
    "order_id", "customer_id", "phone", "city", "delivered_or_returned_date", "return_reason",
    "cod_amount", "courier_fee", "data_source",
)
HEADER_ALIASES = {
    "courier": "courier_name", "courier_company": "courier_name",
    "booking_date": "booked_date", "booked_on": "booked_date", "dispatch_date": "booked_date",
    "delivered_date": "delivered_or_returned_date", "returned_date": "delivered_or_returned_date",
    "closed_date": "delivered_or_returned_date", "delivery_date": "delivered_or_returned_date",
    "reason": "return_reason", "cod": "cod_amount", "cod_value": "cod_amount",
    "fee": "courier_fee", "charges": "courier_fee", "mobile": "phone",
}
LINK_WINDOW_DAYS = 3
MAX_REASON = 500
MAX_MONEY = Decimal("9999999.99")
DATA_SOURCE = "import"

# Order matters: a returned parcel is often written "undelivered" or "not delivered", which also
# contains "deliver"; and "lost" must win over the rest.
_LOST = re.compile(r"\blost\b|missing", re.IGNORECASE)
_RETURNED = re.compile(r"return|\brto\b|refus|undeliver|not\s+deliver|reject|cancel", re.IGNORECASE)
_IN_TRANSIT = re.compile(r"transit|dispatch|booked|pending|out\s+for|shipped|picked|on\s+the\s+way|way", re.IGNORECASE)
_DELIVERED = re.compile(r"deliver|dlvd|received|complete", re.IGNORECASE)
# The reason (or status) says the customer did not take the parcel.
_REFUSED = re.compile(r"refus|inkar|انکار|declin|not\s+accept|rejected", re.IGNORECASE)


def parse_status(text: str) -> str | None:
    """delivered / returned / in_transit / lost from the words couriers use, or None if unclear."""
    if _LOST.search(text):
        return STATUS_LOST
    if _RETURNED.search(text):
        return STATUS_RETURNED
    if _IN_TRANSIT.search(text):
        return STATUS_IN_TRANSIT
    if _DELIVERED.search(text):
        return STATUS_DELIVERED
    return None


@dataclass(frozen=True)
class ShipmentRow:
    row: int
    courier: Name
    city: Name | None
    booked_date: date
    closed_date: date | None
    status: str
    return_reason: str | None
    refused: bool
    cod_amount: Decimal | None
    courier_fee: Decimal | None
    order_ref: str | None            # order_id as written
    customer_ref: str | None         # customer_id as written
    phone: str | None                # +923XXXXXXXXX
    data_source: str | None
    external_id: str = ""


@dataclass
class ShipmentValidation:
    rows: list[ShipmentRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    rejected: int = 0


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


def _money(value: Cell, column: str, row: int, errors: list[RowError]) -> Decimal | None:
    if _as_text(value) is None:
        return None
    number = _to_decimal(value.replace(",", "") if isinstance(value, str) else value)
    if number is None or not (0 <= number <= MAX_MONEY):
        errors.append(RowError(row, column, "Must be an amount of 0 or more, or left blank."))
        return None
    return number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _fingerprint(who: str, courier: str, booked: date, cod: Decimal | None, seen: dict[str, int]) -> str:
    """The id of a shipment: the same parcel always gets the same id (rows that are exactly alike get 2, 3...)."""
    base = "SHP-" + hashlib.sha256(f"{who}|{courier}|{booked.isoformat()}|{cod}".encode()).hexdigest()[:14].upper()
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}-{seen[base]}"


def validate_shipments(parsed: ParsedFile) -> ShipmentValidation:
    positions = _positions(parsed.headers)
    result = ShipmentValidation()
    seen: dict[str, int] = {}
    for sheet_row in parsed.rows:
        n = sheet_row.number

        def cell(column: str) -> Cell:
            i = positions.get(column)
            return sheet_row.values[i] if i is not None and i < len(sheet_row.values) else None

        errors: list[RowError] = []
        courier = normalise_courier(_as_text(cell("courier_name")))
        if courier is None:
            errors.append(RowError(n, "courier_name", "Value is required."))
        elif len(courier.name) > 60:
            errors.append(RowError(n, "courier_name", "Value is longer than 60 characters."))
        city = normalise_city(_as_text(cell("city")))
        if city is not None and len(city.name) > 100:
            errors.append(RowError(n, "city", "Value is longer than 100 characters."))

        raw_status = _as_text(cell("status"))
        status = parse_status(raw_status) if raw_status else None
        if raw_status is None:
            errors.append(RowError(n, "status", "Value is required."))
        elif status is None:
            errors.append(RowError(n, "status", "Must be delivered, returned, in_transit or lost."))

        booked = _parse_date(cell("booked_date"), n, [])  # the message below names the right column
        if booked is None:
            errors.append(RowError(n, "booked_date", "Enter a valid date (DD/MM/YYYY or YYYY-MM-DD) that is not in the future."))
        closed = None
        if _as_text(cell("delivered_or_returned_date")) is not None:
            closed = _parse_date(cell("delivered_or_returned_date"), n, [])
            if closed is None:
                errors.append(RowError(n, "delivered_or_returned_date", "Enter a valid date (DD/MM/YYYY or YYYY-MM-DD) that is not in the future."))
        if status in CLOSED_STATUSES and closed is None and not any(e.column == "delivered_or_returned_date" for e in errors):
            errors.append(RowError(n, "delivered_or_returned_date", "Needed when the status is delivered or returned."))
        if booked and closed and closed < booked:
            errors.append(RowError(n, "delivered_or_returned_date", "Cannot be before booked_date."))

        reason = _as_text(cell("return_reason"))
        if reason is not None and len(reason) > MAX_REASON:
            errors.append(RowError(n, "return_reason", f"Value is longer than {MAX_REASON} characters."))
        cod = _money(cell("cod_amount"), "cod_amount", n, errors)
        fee = _money(cell("courier_fee"), "courier_fee", n, errors)

        phone_text = _as_text(cell("phone"))
        phone = normalise_pk_phone(phone_text) if phone_text else None
        order_ref, customer_ref = _as_text(cell("order_id")), _as_text(cell("customer_id"))
        data_source = _as_text(cell("data_source"))
        if data_source is not None and len(data_source) > 30:
            errors.append(RowError(n, "data_source", "Value is longer than 30 characters."))

        if errors:
            result.errors.extend(errors)
            result.rejected += 1
            continue
        assert courier and booked and status
        who = order_ref or customer_ref or phone or ""
        refused = bool(_REFUSED.search(raw_status or "") or (reason and _REFUSED.search(reason)))
        result.rows.append(ShipmentRow(
            row=n, courier=courier, city=city, booked_date=booked, closed_date=closed, status=status,
            return_reason=reason, refused=refused and status == STATUS_RETURNED, cod_amount=cod,
            courier_fee=fee, order_ref=order_ref, customer_ref=customer_ref, phone=phone, data_source=data_source,
            external_id=_fingerprint(who, courier.name, booked, cod, seen),
        ))
    return result


# --- linking to orders ----------------------------------------------------------------------------

def _customers_for(db: Session, rows: list[ShipmentRow]) -> dict[str, Customer]:
    """Customers named by id or phone in the file, by the reference used."""
    found: dict[str, Customer] = {}
    refs = {r.customer_ref for r in rows if r.customer_ref} | {r.phone for r in rows if r.phone}
    for start in range(0, len(refs), 1000):
        batch = list(refs)[start : start + 1000]
        for customer in db.scalars(
            select(Customer).where(
                Customer.external_id.in_(batch) | Customer.phone_normalised.in_(batch)
            )
        ):
            found[customer.external_id] = customer
            if customer.phone_normalised:
                found[customer.phone_normalised] = customer
    return found


def link_orders(db: Session, rows: list[ShipmentRow]) -> dict[str, tuple[Order | None, Customer | None]]:
    """external_id of each shipment -> (its order or None, its customer or None). Only certain links are made."""
    by_order_id: dict[str, Order] = {}
    wanted = list({r.order_ref for r in rows if r.order_ref})
    for start in range(0, len(wanted), 1000):
        for order in db.scalars(select(Order).where(Order.external_id.in_(wanted[start : start + 1000]))):
            by_order_id[order.external_id] = order
    customers = _customers_for(db, rows)

    # Orders of the customers that need the date-window search.
    pending = [r for r in rows if not (r.order_ref and r.order_ref in by_order_id)]
    people = {c.id: c for r in pending for c in [customers.get(r.customer_ref or "") or customers.get(r.phone or "")] if c}
    orders_of: dict[int, list[Order]] = {}
    if people:
        low = min(r.booked_date for r in pending) - timedelta(days=LINK_WINDOW_DAYS)
        high = max(r.booked_date for r in pending) + timedelta(days=LINK_WINDOW_DAYS)
        ids = list(people)
        for start in range(0, len(ids), 1000):
            for order in db.scalars(
                select(Order).where(Order.customer_id.in_(ids[start : start + 1000]), Order.order_date.between(low, high))
            ):
                orders_of.setdefault(order.customer_id, []).append(order)

    links: dict[str, tuple[Order | None, Customer | None]] = {}
    for r in rows:
        order = by_order_id.get(r.order_ref or "")
        customer = customers.get(r.customer_ref or "") or customers.get(r.phone or "")
        if order is None and customer is not None:
            order = _only_fitting_order(orders_of.get(customer.id, []), r)
        links[r.external_id] = (order, customer)
    return links


def _only_fitting_order(orders: list[Order], r: ShipmentRow) -> Order | None:
    """The one order of this customer that the shipment fits, or None when none or several fit."""
    near = [o for o in orders if abs((o.order_date - r.booked_date).days) <= LINK_WINDOW_DAYS]
    if r.cod_amount is not None and any(o.order_value == r.cod_amount for o in near):
        near = [o for o in near if o.order_value == r.cod_amount]
    if len(near) == 1:
        return near[0]
    if len(near) > 1:
        gaps = sorted((abs((o.order_date - r.booked_date).days), o.id) for o in near)
        if gaps[0][0] < gaps[1][0]:                       # one is clearly the closest
            return next(o for o in near if o.id == gaps[0][1])
    return None


# --- saving ----------------------------------------------------------------------------------------

@dataclass
class ShipmentImportResult:
    rows_in_file: int = 0
    created: int = 0
    updated: int = 0
    rejected: int = 0
    linked_to_orders: int = 0
    unlinked: int = 0
    orders_updated: int = 0                   # orders that received the courier's result
    new_courier_names: list[str] = field(default_factory=list)
    new_city_names: list[str] = field(default_factory=list)
    error_count: int = 0
    errors: list[dict] = field(default_factory=list)


MAX_STORED_ERRORS = 200


def import_shipments(db: Session, content: bytes, file_type: str, default_source: str = DATA_SOURCE) -> ShipmentImportResult:
    parsed = parse_file(content, file_type)
    checked = validate_shipments(parsed)
    result = ShipmentImportResult(rows_in_file=len(parsed.rows), rejected=checked.rejected)
    problems = sorted(checked.errors, key=lambda e: e.row or 0)
    result.error_count = len(problems)
    result.errors = [e.as_dict() for e in problems[:MAX_STORED_ERRORS]]
    rows = checked.rows
    if rows:
        links = link_orders(db, rows)
        existing = {
            s.external_id: s
            for start in range(0, len(rows), 1000)
            for s in db.scalars(select(Shipment).where(Shipment.external_id.in_([r.external_id for r in rows[start : start + 1000]])))
        }
        for r in rows:
            order, customer = links[r.external_id]
            customer_id = order.customer_id if order is not None else (customer.id if customer is not None else None)
            values = dict(
                order_id=order.id if order is not None else None, customer_id=customer_id,
                courier=r.courier.name, courier_raw=r.courier.raw[:100], city=r.city.name if r.city else None,
                city_raw=r.city.raw[:100] if r.city else None, booked_date=r.booked_date, closed_date=r.closed_date,
                status=r.status, return_reason=r.return_reason, refused=r.refused, cod_amount=r.cod_amount,
                courier_fee=r.courier_fee, source=r.data_source or default_source,
            )
            shipment = existing.get(r.external_id)
            if shipment is None:
                db.add(Shipment(external_id=r.external_id, **values))
                result.created += 1
            else:
                for name, value in values.items():
                    setattr(shipment, name, value)
                result.updated += 1
            if order is None:
                result.unlinked += 1
            else:
                result.linked_to_orders += 1
                # The courier's answer is the real label for this order (Order Risk learns from it).
                # Made-up demo shipments must never become labels, so they are left out.
                is_demo = (r.data_source or default_source) == SOURCE_DEMO
                if not is_demo and r.status in CLOSED_STATUSES and r.closed_date and r.closed_date >= order.order_date:
                    order.outcome, order.outcome_date, order.label_source = r.status, r.closed_date, LABEL_COURIER
                    result.orders_updated += 1
        db.commit()
    result.new_courier_names = sorted({r.courier.name for r in rows if not r.courier.known})
    result.new_city_names = sorted({r.city.name for r in rows if r.city and not r.city.known})
    return result
