"""Make MADE-UP weekly product sales, for demos and the viva of the Season Forecast.

IMPORTANT: this data is SYNTHETIC. It is invented by a simple random recipe (below), so the numbers say
nothing about any real shop. Every row carries data_source = "demo (synthetic)", the pages mark such data,
and it can be deleted with one button or DELETE /api/v1/seasons/sales/demo. The real public data set
(Online Retail II, a UK shop) is converted by convert_uci_product_sales.py instead.

The recipe (a fixed random seed, so the same file comes out every time):
- 100 products, weekly sales from January 2021 to the start of May 2026;
- each product has a base level, a yearly growth, and a boost (or none) in each festival window of
  app/data/seasons.json (Eid ul Fitr, Eid ul Adha, Christmas run-up);
- units each week are random (Poisson) around that level.

Usage (from backend/):
    .venv/Scripts/python.exe scripts/generate_demo_product_sales.py
Then upload data/demo_product_sales_synthetic.csv on the Import Data page (Product sales).
"""

import csv
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.seasons import SEASONS  # noqa: E402

SOURCE = "demo (synthetic)"
COLUMNS = ["product", "date", "units", "data_source"]
FIRST_WEEK = date(2021, 1, 4)           # a Monday
LAST_WEEK = date(2026, 4, 27)           # data runs to the end of this week (3 May 2026)
PRODUCTS = 100


def generate(seed: int = 5, products: int = PRODUCTS) -> list[dict[str, str]]:
    rng = np.random.default_rng(seed)
    weeks = []
    week = FIRST_WEEK
    while week <= LAST_WEEK:
        weeks.append(week)
        week += timedelta(days=7)
    base = rng.lognormal(mean=1.6, sigma=0.8, size=products)                  # typical units per week
    growth = rng.normal(0.12, 0.10, size=products)                            # growth per year
    boost = {s.id: rng.choice([0.0, 0.0, 0.6, 1.2, 2.5], size=products) for s in SEASONS}   # extra sales in each festival window
    rows = []
    for p in range(products):
        for w in weeks:
            level = base[p] * (1 + growth[p]) ** ((w - FIRST_WEEK).days / 365)
            middle = w + timedelta(days=3)
            for season in SEASONS:
                window = season.windows.get(middle.year)
                if window and window.start <= middle <= window.end:
                    level *= 1 + boost[season.id][p]
            rows.append({"product": f"Demo product {p + 1:03d}", "date": w.isoformat(), "units": str(int(rng.poisson(level))), "data_source": SOURCE})
    return rows


def main() -> None:
    target = Path(__file__).resolve().parents[2] / "data" / "demo_product_sales_synthetic.csv"
    rows = generate()
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows):,} SYNTHETIC product-week rows to {target}")
    print("  Every row is marked 'demo (synthetic)'. Do not present these numbers as real results.")


if __name__ == "__main__":
    sys.exit(main())
