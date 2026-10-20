"""The Courier Scorecard: how each courier did in each city.

The rules are written here once, because they are what the numbers MEAN:
- Only CLOSED parcels (delivered or returned) count for a rate. A parcel still on its way, or lost,
  has no result yet, so it is counted separately and kept out of the rates.
- delivery rate = delivered / (delivered + returned); return rate = returned / (delivered + returned).
- Average days to deliver uses delivered parcels only (the day it was delivered minus the day it
  was booked).
- Project rule 2: a group with fewer than `MIN_GROUP_COUNT` closed parcels gets NO rate and no
  average, only "Not enough data yet" and how many more are needed. Counts are always shown.
- Demo (made-up) shipments are kept apart from real ones: see `source` below.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Shipment
from app.models.shipment import SOURCE_DEMO, STATUS_DELIVERED, STATUS_IN_TRANSIT, STATUS_LOST, STATUS_RETURNED
from app.services import cash_tracker, data_rules
from app.services.courier_alerts import ReturnAlert, unusual_returns

Source = Literal["auto", "all", "real", "demo"]
SOURCES = ("auto", "all", "real", "demo")


@dataclass
class Stats:
    courier: str
    city: str | None                 # None = the shipments had no city
    shipments: int
    delivered: int
    returned: int
    lost: int
    in_transit: int
    refused: int
    average_days: float | None       # delivered parcels only; None when not enough data
    closed: int = 0                  # delivered + returned
    delivery_rate: float | None = None
    return_rate: float | None = None
    enough: bool = False
    needed: int = 0                  # more closed parcels needed before a rate is shown
    average_days_to_pay: float | None = None   # COD money: delivery to payment (see cash_tracker.py); needs MIN_GROUP_COUNT paid parcels
    paid_parcels: int = 0

    def __post_init__(self) -> None:
        self.closed = self.delivered + self.returned
        self.enough = data_rules.enough(self.closed)
        self.needed = data_rules.more_needed(self.closed)
        if self.enough:
            self.delivery_rate = self.delivered / self.closed
            self.return_rate = self.returned / self.closed
        else:
            self.average_days = None       # no number is shown that is not earned


@dataclass
class Scorecard:
    source_requested: str
    source_used: str                       # "all", "real" or "demo": what the figures are made of
    real_shipments: int
    demo_shipments: int
    min_group_count: int
    period_days: int | None
    period_start: date | None
    period_end: date | None
    shipments: int                         # in the filtered set
    couriers: list[Stats] = field(default_factory=list)       # each courier over all the (filtered) cities
    rows: list[Stats] = field(default_factory=list)           # each courier in each city
    all_couriers: list[str] = field(default_factory=list)     # for the filters
    all_cities: list[str] = field(default_factory=list)
    alerts: list[ReturnAlert] = field(default_factory=list)   # "Unusual returns" (see courier_alerts.py)


def _source_filter(source: str):
    if source == "demo":
        return Shipment.source == SOURCE_DEMO
    if source == "real":
        return Shipment.source.is_distinct_from(SOURCE_DEMO)
    return None


def _aggregate(db: Session, columns: list, conditions: list) -> list[Stats]:
    delivered = Shipment.status == STATUS_DELIVERED
    stmt = select(
        *columns,
        func.count(),
        func.count().filter(delivered),
        func.count().filter(Shipment.status == STATUS_RETURNED),
        func.count().filter(Shipment.status == STATUS_LOST),
        func.count().filter(Shipment.status == STATUS_IN_TRANSIT),
        func.count().filter(Shipment.refused.is_(True)),
        func.avg(Shipment.closed_date - Shipment.booked_date).filter(delivered),
    ).group_by(*columns)
    for condition in conditions:
        stmt = stmt.where(condition)
    stats = []
    for row in db.execute(stmt):
        courier, city = (row[0], row[1]) if len(columns) == 2 else (row[0], None)
        total, ok, back, lost, moving, refused, days = row[len(columns):]
        stats.append(Stats(courier, city, int(total), int(ok), int(back), int(lost), int(moving), int(refused),
                           None if days is None else round(float(days), 1)))
    return stats


def _fill_days_to_pay(stats: Stats, found: tuple[float | None, int] | None) -> None:
    average, paid = found or (None, 0)
    stats.paid_parcels = paid
    stats.average_days_to_pay = average if data_rules.enough(paid) else None


def compute_scorecard(
    db: Session, *, source: str = "auto", days: int | None = None, city: str | None = None, courier: str | None = None
) -> Scorecard:
    """The scorecard for the chosen source, period, city and courier.

    source "auto" (the default) shows the REAL shipments when there are any, and the demo ones only
    when there is nothing else, so made-up numbers never sit among real ones unannounced.
    """
    real = db.scalar(select(func.count()).select_from(Shipment).where(Shipment.source.is_distinct_from(SOURCE_DEMO))) or 0
    demo = db.scalar(select(func.count()).select_from(Shipment).where(Shipment.source == SOURCE_DEMO)) or 0
    used = source if source != "auto" else ("real" if real else "demo" if demo else "all")

    conditions = [c for c in (_source_filter(used),) if c is not None]
    end = db.scalar(select(func.max(Shipment.booked_date)).where(*conditions)) if conditions else db.scalar(select(func.max(Shipment.booked_date)))
    start = None
    if days is not None and end is not None:
        start = end - timedelta(days=days - 1)
        conditions.append(Shipment.booked_date >= start)
    names = db.execute(select(Shipment.courier, Shipment.city).where(*conditions).distinct()).all() if conditions else db.execute(select(Shipment.courier, Shipment.city).distinct()).all()
    # Alerts compare a courier with the OTHER couriers, so they are worked out before the city/courier filters.
    alerts = unusual_returns(_aggregate(db, [Shipment.courier, Shipment.city], conditions))
    alerts = [a for a in alerts if (not city or a.city == city) and (not courier or a.courier == courier)]
    if city:
        conditions.append(Shipment.city == city)
    if courier:
        conditions.append(Shipment.courier == courier)

    rows = _aggregate(db, [Shipment.courier, Shipment.city], conditions)
    couriers = _aggregate(db, [Shipment.courier], conditions)
    # B3: how long the courier takes to hand over the COD money, shown only with enough paid parcels.
    by_courier, by_city = cash_tracker.paid_stats(db, used)
    for stats in couriers:
        _fill_days_to_pay(stats, by_courier.get(stats.courier))
    for stats in rows:
        _fill_days_to_pay(stats, by_city.get((stats.courier, stats.city)))
    rows.sort(key=lambda s: ((s.city is None), s.city or "", -s.shipments, s.courier))
    couriers.sort(key=lambda s: (-s.shipments, s.courier))
    return Scorecard(
        source_requested=source, source_used=used, real_shipments=int(real), demo_shipments=int(demo),
        min_group_count=data_rules.MIN_GROUP_COUNT, period_days=days, period_start=start, period_end=end,
        shipments=sum(s.shipments for s in couriers), couriers=couriers, rows=rows,
        all_couriers=sorted({n[0] for n in names}), all_cities=sorted({n[1] for n in names if n[1]}), alerts=alerts,
    )


@dataclass
class Suggestion:
    city: str
    available: bool                     # False = no courier in this city has enough history
    source_used: str
    best: Stats | None = None
    others: list[Stats] = field(default_factory=list)   # the other couriers that also have enough history


def suggest_courier(db: Session, city_text: str) -> Suggestion | None:
    """The courier with the lowest return rate in a city, but ONLY among couriers whose history there
    passes the minimum (project rule 2). Returns None when the city text is empty.

    The advice is about past parcels only. The same real-first rule as the scorecard applies, so made-up
    demo data never advises on a business that has real shipments.
    """
    from app.services.names import normalise_city

    name = normalise_city(city_text)
    if name is None:
        return None
    card = compute_scorecard(db, source="auto", city=name.name)
    ranked = sorted((r for r in card.rows if r.enough and r.city == name.name), key=lambda r: (r.return_rate, -r.closed))
    if not ranked:
        return Suggestion(name.name, False, card.source_used)
    return Suggestion(name.name, True, card.source_used, ranked[0], ranked[1:])
