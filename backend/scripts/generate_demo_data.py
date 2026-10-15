"""Generate a SYNTHETIC customer-orders CSV for testing imports and analytics.

Every value is made up: IDs start with "SYN-", emails use example.com, and the
data must never be presented as real business results. A fixed seed makes the
output reproducible.

Usage (from backend/):
    .venv/Scripts/python.exe scripts/generate_demo_data.py [output.csv]

Default output: ../data/demo_orders_synthetic.csv (the data/ folder is gitignored).
"""

import csv
import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

SEED = 20261015
CUSTOMERS = 300
END = date(2026, 10, 14)  # last possible order date (no future dates)
START = date(2025, 4, 1)

FIRST_NAMES = [
    "Amelia", "Noah", "Liam", "Sofia", "Maya", "Ethan", "Grace", "Omar", "Hana",
    "Lucas", "Chloe", "Daniel", "Isabella", "Jonas", "Ayesha", "Bilal", "Fatima",
    "Hamza", "Zara", "Ali", "Mei", "Kenji", "Priya", "Arjun", "Elena", "Mateo",
    "Lena", "Yusuf", "Nora", "Sami",
]
LAST_NAMES = [
    "Chen", "Patel", "Okafor", "Alvarez", "Singh", "Brooks", "Muller", "Haddad",
    "Kim", "Silva", "Martin", "Nguyen", "Rossi", "Berg", "Khan", "Ahmed", "Malik",
    "Sato", "Iyer", "Garcia", "Novak", "Hassan", "Weber", "Costa",
]
COUNTRIES = ["US", "UK", "PK", "DE", "CA", "AU", "AE", "IN", "FR", "ES"]
CHANNELS = ["Shopify", "WooCommerce", "Magento"]
CATEGORIES = ["Skincare", "Haircare", "Fragrance", "Bodycare", "Makeup", "Bundles", "Accessories"]


@dataclass(frozen=True)
class Profile:
    """A behaviour pattern. Not written to the file — analytics must infer it."""

    share: float
    gap_days: tuple[int, int]        # days between orders
    order_count: tuple[int, int]
    aov: tuple[float, float]         # average order value range
    last_order_ago: tuple[int, int]  # days before END of the most recent order
    engagement: tuple[int, int]


PROFILES = {
    "frequent_high_value": Profile(0.10, (18, 35), (10, 22), (120, 260), (0, 20), (75, 98)),
    "regular": Profile(0.20, (30, 60), (6, 12), (60, 130), (5, 45), (60, 85)),
    "new_promising": Profile(0.20, (14, 40), (1, 4), (55, 120), (0, 60), (55, 88)),
    "going_quiet": Profile(0.25, (30, 70), (4, 10), (50, 140), (90, 210), (25, 55)),
    "lapsed": Profile(0.25, (40, 120), (1, 3), (25, 75), (240, 500), (5, 30)),
}


def pick_profile(rng: random.Random) -> str:
    roll, total = rng.random(), 0.0
    for name, profile in PROFILES.items():
        total += profile.share
        if roll < total:
            return name
    return "lapsed"


def generate(rng: random.Random) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    order_number = 100000
    for index in range(1, CUSTOMERS + 1):
        profile = PROFILES[pick_profile(rng)]
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        customer = {
            "customer_id": f"SYN-C{index:04d}",
            "email": f"{first.lower()}.{last.lower()}.{index}@example.com",
            "first_name": first,
            "last_name": last,
            "country": rng.choice(COUNTRIES),
            "channel": rng.choice(CHANNELS),
        }
        base_aov = rng.uniform(*profile.aov)
        base_engagement = rng.randint(*profile.engagement)
        has_engagement = rng.random() > 0.2  # ~20% of customers never report it

        # Walk backwards from the most recent order so recency matches the profile.
        current = END - timedelta(days=rng.randint(*profile.last_order_ago))
        dates: list[date] = []
        for _ in range(rng.randint(*profile.order_count)):
            if current < START:
                break
            dates.append(current)
            current -= timedelta(days=rng.randint(*profile.gap_days))
        if not dates:
            dates.append(max(START, END - timedelta(days=rng.randint(*profile.last_order_ago))))

        for order_date in sorted(dates):
            order_number += 1
            value = max(5.0, rng.gauss(base_aov, base_aov * 0.25))
            engagement = ""
            if has_engagement:
                engagement = str(max(0, min(100, base_engagement + rng.randint(-6, 6))))
            rows.append(
                {
                    "customer_id": customer["customer_id"],
                    "email": customer["email"],
                    "order_id": f"SYN-O{order_number}",
                    "order_date": order_date.isoformat(),
                    "order_value": f"{value:.2f}",
                    "first_name": customer["first_name"],
                    "last_name": customer["last_name"],
                    "country": customer["country"],
                    "product_category": rng.choice(CATEGORIES),
                    "channel": customer["channel"],
                    "engagement": engagement,
                }
            )
    rows.sort(key=lambda r: (r["order_date"], r["order_id"]))
    return rows


def main() -> None:
    default = Path(__file__).resolve().parents[2] / "data" / "demo_orders_synthetic.csv"
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = generate(random.Random(SEED))
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    customers = len({r["customer_id"] for r in rows})
    print(f"Wrote {len(rows)} synthetic orders for {customers} customers to {output}")


if __name__ == "__main__":
    main()
