"""Make MADE-UP courier payments for the demo shipments, so the Cash Tracker has something to show.

IMPORTANT: this data is SYNTHETIC, exactly like generate_demo_shipments.py. Every row carries
data_source = "demo (synthetic)", the pages mark such data, and it can be deleted with one button
or DELETE /api/v1/cash/payments/demo. Never present these numbers as real results.

The recipe (a fixed random seed, so the same file comes out every time):
- each courier pays in batches: TCS about every 7 days, Leopards every 14, Trax every 10, PostEx every 21
  (the slow payer, so the tracker has a courier to flag);
- a batch pays the delivered COD parcels that are at least the courier's usual delay old, by roughly
  95% of their value (couriers often short-pay a little);
- the last weeks of the data are left unpaid, as they would be in real life.

Usage (from backend/):
    .venv/Scripts/python.exe scripts/generate_demo_payments.py
It reads data/demo_shipments_synthetic.csv (make it with generate_demo_shipments.py first) and writes
data/demo_payments_synthetic.csv. Upload that on the Import Data page (Courier payments).
"""

import csv
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

SOURCE = "demo (synthetic)"
COLUMNS = ["courier_name", "payment_date", "amount", "reference", "order_ids", "data_source"]
EVERY_DAYS = {"TCS": 7, "Leopards": 14, "Trax": 10, "PostEx": 21}
MIN_AGE_DAYS = {"TCS": 3, "Leopards": 6, "Trax": 5, "PostEx": 9}


def generate(shipments: list[dict[str, str]], seed: int = 11) -> list[dict[str, str]]:
    """One batch payment per courier per period. `shipments` are rows of the demo shipments file."""
    rng = random.Random(seed)
    parcels = defaultdict(list)                      # courier -> [(delivered date, cod amount)]
    last_day = date.min
    for r in shipments:
        if r["status"] == "delivered" and r["cod_amount"] and r["delivered_or_returned_date"]:
            when = date.fromisoformat(r["delivered_or_returned_date"])
            parcels[r["courier_name"]].append((when, Decimal(r["cod_amount"])))
            last_day = max(last_day, when)
    rows = []
    for courier, items in sorted(parcels.items()):
        every, min_age = EVERY_DAYS.get(courier, 14), MIN_AGE_DAYS.get(courier, 5)
        items.sort()
        paid_up_to = items[0][0] - timedelta(days=1)
        pay_day = items[0][0] + timedelta(days=every)
        number = 0
        while pay_day <= last_day - timedelta(days=every * 2):      # the most recent weeks stay unpaid
            batch = [amount for when, amount in items if paid_up_to < when <= pay_day - timedelta(days=min_age)]
            if batch:
                number += 1
                total = sum(batch, Decimal("0")) * Decimal(str(rng.uniform(0.93, 0.98)))
                rows.append({
                    "courier_name": courier, "payment_date": pay_day.isoformat(), "amount": f"{total:.2f}",
                    "reference": f"DEMO-{courier.upper()}-{number:03d}", "order_ids": "", "data_source": SOURCE,
                })
                paid_up_to = pay_day - timedelta(days=min_age)
            pay_day += timedelta(days=every)
    return rows


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "data" / "demo_shipments_synthetic.csv"
    if not source.exists():
        raise SystemExit(f"{source} not found. Make it first with scripts/generate_demo_shipments.py.")
    with source.open(newline="", encoding="utf-8") as handle:
        shipments = list(csv.DictReader(handle))
    rows = generate(shipments)
    target = root / "data" / "demo_payments_synthetic.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    total = sum(Decimal(r["amount"]) for r in rows)
    print(f"Wrote {len(rows):,} SYNTHETIC payments (Rs {total:,.0f} in total) to {target}")
    print("  Every row is marked 'demo (synthetic)'. Do not present these numbers as real results.")


if __name__ == "__main__":
    sys.exit(main())
