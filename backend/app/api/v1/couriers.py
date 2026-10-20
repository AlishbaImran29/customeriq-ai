"""Courier Scorecard endpoint."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.schemas.couriers import CourierStatsOut, ScorecardOut
from app.services.courier_scorecard import SOURCES, Stats, compute_scorecard

router = APIRouter(prefix="/couriers", tags=["couriers"])


def _out(s: Stats) -> CourierStatsOut:
    return CourierStatsOut(
        courier=s.courier, city=s.city, shipments=s.shipments, closed=s.closed, delivered=s.delivered,
        returned=s.returned, lost=s.lost, in_transit=s.in_transit, refused=s.refused,
        delivery_rate=s.delivery_rate, return_rate=s.return_rate, average_days=s.average_days,
        enough=s.enough, needed=s.needed,
    )


@router.get("/scorecard", response_model=ScorecardOut, summary="How each courier did in each city")
def scorecard(
    source: str = Query("auto", description="auto (real if there is any, else demo), all, real or demo"),
    days: int | None = Query(None, ge=1, le=3650, description="Only parcels booked in the last N days of data"),
    city: str | None = Query(None, max_length=100),
    courier: str | None = Query(None, max_length=60),
    db: Session = Depends(get_db),
) -> ScorecardOut:
    """Rates are shown only for groups with enough closed parcels; the others say how many more are needed."""
    if source not in SOURCES:
        raise ApiError(422, "invalid_source", "source must be one of: " + ", ".join(SOURCES) + ".")
    card = compute_scorecard(db, source=source, days=days, city=city or None, courier=courier or None)
    return ScorecardOut(
        source_requested=card.source_requested, source_used=card.source_used, real_shipments=card.real_shipments,
        demo_shipments=card.demo_shipments, min_group_count=card.min_group_count, period_days=card.period_days,
        period_start=card.period_start, period_end=card.period_end, shipments=card.shipments,
        couriers=[_out(s) for s in card.couriers], rows=[_out(s) for s in card.rows],
        all_couriers=card.all_couriers, all_cities=card.all_cities,
    )
