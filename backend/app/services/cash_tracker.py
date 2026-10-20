"""The Cash Tracker: COD money couriers still owe the seller.

COD = cash on delivery: the courier collects the price from the customer and hands it over later.
Owed money is worked out with the plain FIFO rules in cash_matching.py; this file only collects the
data and adds it up. No machine learning, no estimates: every figure is a sum of recorded amounts.

Rules:
- Only DELIVERED parcels with a COD amount are owed. Returned parcels collected nothing.
- Real data is used when there is any; demo (made-up) data only when there is nothing else.
- Money sums always show. "Average days to pay" is a conclusion about a courier, so it follows the
  minimum-count rule: it needs at least MIN_GROUP_COUNT fully paid parcels (project rule 2).
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CourierPayment, Order, Shipment
from app.models.shipment import SOURCE_DEMO, STATUS_DELIVERED
from app.services import cash_config, data_rules
from app.services.cash_matching import PAID, PARTLY, PENDING, Parcel, Payment, match
from app.services.payment_import import split_order_refs


@dataclass
class CashParcel(Parcel):
    city: str | None = None
    shipment_ref: str = ""          # the order's id if linked, else the shipment's own id


@dataclass
class CourierCash:
    courier: str
    delivered_cod: Decimal
    received: Decimal
    pending: Decimal
    unpaid_parcels: int             # pending + partly paid
    paid_parcels: int
    oldest_pending_days: int | None
    average_days_to_pay: float | None
    enough: bool                    # enough fully paid parcels for the average
    needed: int
    credit: Decimal                 # paid in advance / more than owed
    overdue_amount: Decimal         # still owed on parcels older than the alert threshold
    overdue_parcels: int


@dataclass
class Bucket:
    label: str                      # "0-7", "8-14", "15+"
    parcels: int
    amount: Decimal


@dataclass
class Tracker:
    as_of: date
    alert_days: int
    source_used: str
    real_cod_parcels: int
    demo_cod_parcels: int
    payments: int
    min_group_count: int
    delivered_cod: Decimal
    received: Decimal
    pending: Decimal
    credit: Decimal
    unpaid_parcels: int
    oldest_pending_days: int | None
    couriers: list[CourierCash] = field(default_factory=list)
    buckets: list[Bucket] = field(default_factory=list)
    alerts: list[CourierCash] = field(default_factory=list)       # couriers with money overdue


def _is_demo(column):
    return column == SOURCE_DEMO


def _load(db: Session, source: str) -> tuple[str, int, int, list[CashParcel], list[Payment]]:
    base = (Shipment.status == STATUS_DELIVERED, Shipment.cod_amount > 0, Shipment.closed_date.is_not(None))
    real = db.scalar(select(func.count()).select_from(Shipment).where(*base, Shipment.source.is_distinct_from(SOURCE_DEMO))) or 0
    demo = db.scalar(select(func.count()).select_from(Shipment).where(*base, _is_demo(Shipment.source))) or 0
    used = source if source in ("real", "demo") else ("real" if real else "demo" if demo else "real")
    shipment_filter = _is_demo(Shipment.source) if used == "demo" else Shipment.source.is_distinct_from(SOURCE_DEMO)
    payment_filter = _is_demo(CourierPayment.source) if used == "demo" else CourierPayment.source.is_distinct_from(SOURCE_DEMO)

    parcels = [
        CashParcel(
            key=s.id, courier=s.courier, delivered_on=s.closed_date, amount=Decimal(s.cod_amount),
            order_ref=order_ref, city=s.city, shipment_ref=order_ref or s.external_id,
        )
        for s, order_ref in db.execute(
            select(Shipment, Order.external_id).join(Order, Order.id == Shipment.order_id, isouter=True).where(*base, shipment_filter)
        )
    ]
    payments = [
        Payment(key=p.id, courier=p.courier, paid_on=p.payment_date, amount=Decimal(p.amount), order_refs=split_order_refs(p.order_refs))
        for p in db.scalars(select(CourierPayment).where(payment_filter))
    ]
    return used, int(real), int(demo), parcels, payments


def _today(used: str, parcels: list[CashParcel], payments: list[Payment], as_of: date | None) -> date:
    """"Today" for the ages. Real data: the real today. Demo data is old (the public dataset is from 2011),
    so its "today" is the last day in the demo data, otherwise every demo parcel would look years overdue."""
    if as_of:
        return as_of
    if used == "demo" and (parcels or payments):
        return max([p.delivered_on for p in parcels] + [p.paid_on for p in payments])
    return date.today()


def _average(parcels: list[CashParcel]) -> tuple[float | None, int]:
    days = [p.days_to_pay for p in parcels if p.status == PAID and p.days_to_pay is not None]
    return (round(sum(days) / len(days), 1) if days else None), len(days)


def compute_tracker(db: Session, *, alert_days: int | None = None, as_of: date | None = None, source: str = "auto") -> Tracker:
    alert_days = cash_config.ALERT_DAYS if alert_days is None else alert_days
    used, real, demo, parcels, payments = _load(db, source)
    today = _today(used, parcels, payments, as_of)
    credit = match(parcels, payments)

    by_courier: dict[str, list[CashParcel]] = {}
    for p in parcels:
        by_courier.setdefault(p.courier, []).append(p)

    couriers: list[CourierCash] = []
    for name, items in by_courier.items():
        unpaid = [p for p in items if p.status != PAID]
        average, paid_count = _average(items)
        enough = data_rules.enough(paid_count)
        overdue = [p for p in unpaid if (today - p.delivered_on).days > alert_days]
        couriers.append(CourierCash(
            courier=name, delivered_cod=sum((p.amount for p in items), Decimal("0")),
            received=sum((p.paid for p in items), Decimal("0")), pending=sum((p.due for p in unpaid), Decimal("0")),
            unpaid_parcels=len(unpaid), paid_parcels=paid_count,
            oldest_pending_days=max(((today - p.delivered_on).days for p in unpaid), default=None),
            average_days_to_pay=average if enough else None, enough=enough, needed=data_rules.more_needed(paid_count),
            credit=credit.get(name, Decimal("0")), overdue_amount=sum((p.due for p in overdue), Decimal("0")),
            overdue_parcels=len(overdue),
        ))
    couriers.sort(key=lambda c: (-c.pending, c.courier))

    unpaid_all = [p for p in parcels if p.status != PAID]
    edges = cash_config.BUCKET_EDGES
    labels = [f"0-{edges[0]}", f"{edges[0] + 1}-{edges[1]}", f"{edges[1] + 1}+"]
    buckets = [Bucket(label, 0, Decimal("0")) for label in labels]
    for p in unpaid_all:
        age = (today - p.delivered_on).days
        b = buckets[0 if age <= edges[0] else 1 if age <= edges[1] else 2]
        b.parcels += 1
        b.amount += p.due

    return Tracker(
        as_of=today, alert_days=alert_days, source_used=used, real_cod_parcels=real, demo_cod_parcels=demo,
        payments=len(payments), min_group_count=data_rules.MIN_GROUP_COUNT,
        delivered_cod=sum((p.amount for p in parcels), Decimal("0")), received=sum((p.paid for p in parcels), Decimal("0")),
        pending=sum((p.due for p in unpaid_all), Decimal("0")), credit=sum(credit.values(), Decimal("0")),
        unpaid_parcels=len(unpaid_all),
        oldest_pending_days=max(((today - p.delivered_on).days for p in unpaid_all), default=None),
        couriers=couriers, buckets=buckets,
        alerts=sorted((c for c in couriers if c.overdue_parcels > 0), key=lambda c: -c.overdue_amount),
    )


@dataclass
class PendingRow:
    courier: str
    city: str | None
    reference: str
    delivered_on: date
    days_pending: int
    cod_amount: Decimal
    paid: Decimal
    still_owed: Decimal
    status: str                     # "pending" or "partly_paid"


def pending_list(db: Session, *, as_of: date | None = None, source: str = "auto", limit: int = 5000) -> list[PendingRow]:
    """The parcels still unpaid (or partly paid), oldest first: the list to chase the courier with."""
    used, _, _, parcels, payments = _load(db, source)
    today = _today(used, parcels, payments, as_of)
    match(parcels, payments)
    rows = [
        PendingRow(p.courier, p.city, p.shipment_ref, p.delivered_on, (today - p.delivered_on).days, p.amount, p.paid, p.due, p.status)
        for p in parcels if p.status in (PENDING, PARTLY)
    ]
    rows.sort(key=lambda r: (r.delivered_on, r.courier, r.reference))
    return rows[:limit]


def paid_stats(db: Session, used: str) -> tuple[dict[str, tuple[float | None, int]], dict[tuple[str, str | None], tuple[float | None, int]]]:
    """Average days to pay per courier and per courier + city (for the scorecard), with the count of paid parcels
    behind each. Callers apply the minimum-count rule."""
    _, _, _, parcels, payments = _load(db, used if used in ("real", "demo") else "auto")
    match(parcels, payments)
    per_courier: dict[str, list[CashParcel]] = {}
    per_city: dict[tuple[str, str | None], list[CashParcel]] = {}
    for p in parcels:
        per_courier.setdefault(p.courier, []).append(p)
        per_city.setdefault((p.courier, p.city), []).append(p)
    return {k: _average(v) for k, v in per_courier.items()}, {k: _average(v) for k, v in per_city.items()}
