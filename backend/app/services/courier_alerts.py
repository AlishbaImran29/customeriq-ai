"""The "Unusual returns" alert: is one courier's return rate in a city clearly worse than the others'?

A two-proportion z-test compares the courier's returned/finished with ALL OTHER couriers in the same
city. It is used instead of "looks higher" because small groups jump around by chance: the test
asks "how likely is a gap this big if the courier were really the same as the rest?".

Safeguards (project rule 2, and honesty about chance):
- BOTH groups need at least MIN_GROUP_COUNT finished parcels, or no alert is made.
- Only a HIGHER return rate alerts, and only when the gap is at least MIN_GAP and the one-sided
  p-value is below ALERT_P_VALUE (0.01, stricter than the usual 0.05 because many couriers x cities
  are checked at once, which would otherwise raise false alarms).
- The alert reports counts, never a verdict: high returns can also come from customers or products.
"""

from dataclasses import dataclass
from math import erfc, sqrt

from app.services import data_rules

ALERT_P_VALUE = 0.01
MIN_GAP = 0.05           # at least 5 percentage points worse than the others


@dataclass(frozen=True)
class ReturnAlert:
    courier: str
    city: str
    returned: int
    closed: int
    rate: float
    others_returned: int
    others_closed: int
    others_rate: float
    p_value: float


def one_sided_p(returned_a: int, closed_a: int, returned_b: int, closed_b: int) -> float:
    """P(a gap at least this big in A's favour of being WORSE by chance), two-proportion z-test."""
    pooled = (returned_a + returned_b) / (closed_a + closed_b)
    spread = sqrt(pooled * (1 - pooled) * (1 / closed_a + 1 / closed_b))
    if spread == 0:
        return 1.0
    z = (returned_a / closed_a - returned_b / closed_b) / spread
    return 0.5 * erfc(z / sqrt(2))       # upper tail of the normal distribution


def unusual_returns(groups) -> list[ReturnAlert]:
    """`groups`: objects with courier, city, returned, closed (one per courier and city)."""
    by_city: dict[str, list] = {}
    for g in groups:
        if g.city:
            by_city.setdefault(g.city, []).append(g)
    alerts = []
    for city, members in by_city.items():
        for g in members:
            others_closed = sum(o.closed for o in members if o is not g)
            others_returned = sum(o.returned for o in members if o is not g)
            if not (data_rules.enough(g.closed) and data_rules.enough(others_closed)):
                continue
            rate, others_rate = g.returned / g.closed, others_returned / others_closed
            p = one_sided_p(g.returned, g.closed, others_returned, others_closed)
            if rate - others_rate >= MIN_GAP and p < ALERT_P_VALUE:
                alerts.append(ReturnAlert(g.courier, city, g.returned, g.closed, rate,
                                          others_returned, others_closed, others_rate, p))
    return sorted(alerts, key=lambda a: a.p_value)
