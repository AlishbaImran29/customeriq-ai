"""Response shape of the Courier Scorecard (camelCase, matching frontend/lib/types.ts)."""

from datetime import date

from app.schemas.imports import CamelModel


class CourierStatsOut(CamelModel):
    courier: str
    city: str | None                  # None = no city was given for these shipments
    shipments: int                    # all of them, whatever their status
    closed: int                       # delivered + returned: the parcels a rate is worked out from
    delivered: int
    returned: int
    lost: int
    in_transit: int
    refused: int                      # returned parcels where the customer refused
    delivery_rate: float | None       # 0-1; None when there is not enough data
    return_rate: float | None
    average_days: float | None        # booked to delivered, delivered parcels only
    enough: bool                      # closed >= the minimum count
    needed: int                       # more closed parcels needed before the rates are shown
    average_days_to_pay: float | None # COD money: delivery to payment; None without enough paid parcels
    paid_parcels: int                 # fully paid COD parcels behind that average


class ReturnAlertOut(CamelModel):
    courier: str
    city: str
    returned: int
    closed: int
    rate: float
    others_returned: int
    others_closed: int
    others_rate: float
    p_value: float


class ScorecardOut(CamelModel):
    source_requested: str
    source_used: str                  # "all", "real" or "demo": what the figures are made of
    real_shipments: int
    demo_shipments: int               # made-up shipments (marked "demo (synthetic)")
    min_group_count: int
    period_days: int | None
    period_start: date | None
    period_end: date | None
    shipments: int
    couriers: list[CourierStatsOut]   # each courier over the cities shown
    rows: list[CourierStatsOut]       # each courier in each city
    all_couriers: list[str]
    all_cities: list[str]
    alerts: list[ReturnAlertOut]      # unusually high return rates (both groups passed the minimum)


class SuggestionOut(CamelModel):
    city: str
    available: bool                   # False = "No courier has enough history in this city yet."
    source_used: str                  # "demo" when the history is made up
    best: CourierStatsOut | None
    others: list[CourierStatsOut]
