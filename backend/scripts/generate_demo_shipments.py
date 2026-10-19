"""Make MADE-UP courier shipments for the public Online Retail II orders, for demos and the viva.

IMPORTANT: this data is SYNTHETIC. The Online Retail II dataset is a UK shop and has no couriers or
Pakistani cities at all, so these shipments are invented by a simple random recipe (below). They are
useful only to show the Courier Scorecard and Cash Tracker working. Every row carries
data_source = "demo (synthetic)", the pages mark such data, and it can be deleted with one button
(Import Data page) or DELETE /api/v1/shipments/demo. Never present these numbers as real results.

The recipe (a fixed random seed, so the same file comes out every time):
- each chosen order gets one courier and one Pakistani city;
- a base return rate per city, times a small factor per courier;
- one planted pattern, so there is something for the "unusual returns" alert to find:
  Leopards returns about 2.2 times more often than the other couriers in Multan;
- parcels booked in the last days of the data are still "in_transit".

Usage (from backend/):
    .venv/Scripts/python.exe scripts/generate_demo_shipments.py
Then upload data/demo_shipments_synthetic.csv on the Import Data page (Courier shipments).
"""

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

SOURCE = "demo (synthetic)"
COURIERS = {"TCS": 0.38, "Leopards": 0.28, "Trax": 0.20, "PostEx": 0.14}
COURIER_FACTOR = {"TCS": 0.9, "Leopards": 1.0, "Trax": 1.1, "PostEx": 1.0}
CITIES = {
    "Karachi": (0.26, 0.16), "Lahore": (0.24, 0.14), "Islamabad": (0.12, 0.12), "Rawalpindi": (0.08, 0.13),
    "Faisalabad": (0.08, 0.15), "Multan": (0.07, 0.16), "Peshawar": (0.08, 0.20), "Quetta": (0.04, 0.24),
    "Sialkot": (0.03, 0.14),
}  # city -> (share of parcels, base return rate)
PLANTED = ("Leopards", "Multan", 2.2)          # (courier, city, times more returns than usual)
MESSY_COURIER = {"TCS": ["t.c.s", "TCS ", "Tcs Express"], "Leopards": ["leopard courier", "LEOPARDS"], "Trax": ["trax pk"], "PostEx": ["post ex"]}
MESSY_CITY = {"Islamabad": ["Isb", "islamabad "], "Rawalpindi": ["pindi", "RWP"], "Karachi": ["khi"], "Lahore": ["lhr"], "Multan": ["multan "]}
IN_TRANSIT_DAYS = 5
COLUMNS = [
    "order_id", "customer_id", "phone", "courier_name", "city", "booked_date", "delivered_or_returned_date",
    "status", "return_reason", "cod_amount", "courier_fee", "data_source",
]


def _pick(rng: random.Random, weights: dict) -> str:
    return rng.choices(list(weights), weights=[w if not isinstance(w, tuple) else w[0] for w in weights.values()])[0]


def generate(orders: list[tuple[str, str, date, float]], seed: int = 42) -> list[dict[str, str]]:
    """Shipments for (order_id, customer_id, order_date, value) orders. Pure: the same input and seed
    always give the same rows."""
    rng = random.Random(seed)
    last_day = max(o[2] for o in orders)
    rows = []
    for order_id, customer_id, order_date, value in sorted(orders, key=lambda o: (o[2], o[0])):
        courier, city = _pick(rng, COURIERS), _pick(rng, CITIES)
        rate = CITIES[city][1] * COURIER_FACTOR[courier]
        if (courier, city) == PLANTED[:2]:
            rate *= PLANTED[2]
        booked = order_date + timedelta(days=1)
        days = 2 + int(rng.expovariate(0.7)) + (1 if city in ("Quetta", "Peshawar") else 0)
        closed = booked + timedelta(days=days)
        row = {
            "order_id": order_id, "customer_id": customer_id, "phone": "",
            "courier_name": rng.choice([courier] * 4 + MESSY_COURIER[courier]),
            "city": rng.choice([city] * 5 + MESSY_CITY.get(city, [city])),
            "booked_date": booked.isoformat(), "delivered_or_returned_date": "", "status": "in_transit",
            "return_reason": "", "cod_amount": f"{value:.2f}", "courier_fee": str(rng.choice(range(150, 401, 10))),
            "data_source": SOURCE,
        }
        if closed > last_day or booked > last_day - timedelta(days=IN_TRANSIT_DAYS):
            pass                                                           # still on its way
        elif rng.random() < 0.005:
            row["status"] = "lost"
        elif rng.random() < rate:
            row.update(status="returned", delivered_or_returned_date=closed.isoformat(),
                       return_reason=rng.choice(["Customer refused", "Customer refused to accept", "Address not found", "Customer not available"]))
        else:
            row.update(status="delivered", delivered_or_returned_date=closed.isoformat())
        rows.append(row)
    return rows


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "data" / "public_uci_online_retail_ii.csv"
    if not source.exists():
        raise SystemExit(f"{source} not found. Make it first with scripts/convert_uci_online_retail.py.")
    with source.open(newline="", encoding="utf-8") as handle:
        orders = [
            (r["order_id"], r["customer_id"], date.fromisoformat(r["order_date"]), float(r["order_value"]))
            for r in csv.DictReader(handle) if "2011-01-01" <= r["order_date"] <= "2011-12-09"
        ]
    rng = random.Random(7)
    chosen = rng.sample(orders, k=min(6000, len(orders)))
    rows = generate(chosen)
    target = root / "data" / "demo_shipments_synthetic.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    closed = [r for r in rows if r["status"] in ("delivered", "returned")]
    returned = [r for r in closed if r["status"] == "returned"]
    print(f"Wrote {len(rows):,} SYNTHETIC shipments to {target}")
    print(f"  closed: {len(closed):,}, returned: {len(returned):,} ({len(returned) / max(1, len(closed)):.1%}), "
          f"in transit/lost: {len(rows) - len(closed):,}")
    print("  Every row is marked 'demo (synthetic)'. Do not present these numbers as real results.")


if __name__ == "__main__":
    sys.exit(main())
