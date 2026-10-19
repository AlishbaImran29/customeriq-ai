"""Train the Order Risk model and print the honest report: model vs baseline, and the decision.

Usage (from backend/):
    .venv/Scripts/python.exe scripts/train_order_risk.py                # orders in the database
    .venv/Scripts/python.exe scripts/train_order_risk.py --csv FILE     # a CustomerIQ import file, no database
    add --save to store the result in the database (needs the database; not with --csv)
    add --shipping-cost N to also print the savings estimate (N = shipping cost per parcel, both ways)

The CSV must have the Order Risk columns (see scripts/convert_uci_online_retail.py).
"""

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.order_features import OrderInput  # noqa: E402
from app.services.order_risk_model import OrderRiskResult, train_order_risk  # noqa: E402
from app.services.order_risk_savings import SavingsEstimate, savings_estimate  # noqa: E402


def read_csv(path: Path) -> list[OrderInput]:
    def whole(text: str) -> int | None:
        return int(text) if text else None

    with path.open(newline="", encoding="utf-8") as handle:
        return [
            OrderInput(
                order_id=r["order_id"],
                customer_id=r["customer_id"],
                order_date=date.fromisoformat(r["order_date"]),
                value=float(r["order_value"]),
                ordered_at=datetime.fromisoformat(r["order_datetime"]) if r.get("order_datetime") else None,
                item_count=whole(r.get("item_count", "")),
                distinct_products=whole(r.get("distinct_products", "")),
                country=r.get("country") or None,
                outcome=r.get("outcome") or None,
                outcome_date=date.fromisoformat(r["outcome_date"]) if r.get("outcome_date") else None,
                label_source=r.get("label_source") or None,
            )
            for r in csv.DictReader(handle)
        ]


def print_report(result: OrderRiskResult) -> None:
    pct = lambda v: "-" if v is None else f"{v:.1%}"  # noqa: E731
    num = lambda v: "-" if v is None else f"{v:.3f}"  # noqa: E731
    print(f"Decision: {result.status.upper()}")
    print(f"Label source: {result.label_source}")
    print(f"Latest order: {result.as_of}; labels count only for orders older than {result.maturity_days} days")
    print(f"Training: orders up to {result.train_end} ({result.train_rows:,} orders)")
    print(f"Testing:  orders from {result.split_date} ({result.test_rows:,} orders, "
          f"{pct(result.test_return_rate)} really returned)")
    print(f"{result.metric}:  model {num(result.model_auc)}   baseline {num(result.baseline_auc)}")
    print(f"Riskiest {result.top_fraction:.0%} of orders, share really returned:  "
          f"model {pct(result.model_precision_top)}   baseline {pct(result.baseline_precision_top)}")
    if result.reason:
        print(f"Reason: {result.reason}")
    if result.available:
        coefficients = result.pipeline.named_steps["model"].coef_[0]
        print("Strongest features (scaled coefficients, + = more likely returned):")
        for name, value in sorted(zip(result.feature_names, coefficients), key=lambda x: -abs(x[1]))[:8]:
            print(f"  {value:+.2f}  {name}")


def print_savings(est: SavingsEstimate) -> None:
    pct = lambda v: "-" if v is None else f"{v:.1%}"  # noqa: E731
    print()
    print(f"Savings ESTIMATE on past orders ({est.test_start} to {est.test_end}, {est.test_orders:,} orders)")
    print(f"  Flagged {', '.join(est.flagged_levels)}: {est.flagged_orders:,} orders, "
          f"{est.flagged_returned:,} really returned ({pct(est.flagged_precision)}), {est.false_alarms:,} false alarms")
    print(f"  All returned orders in the period: {est.total_returned:,}; flagged caught {pct(est.returns_caught)} of them")
    print(f"  Shipping cost per parcel (both ways): {est.shipping_cost:,.2f}")
    print(f"  Estimated cost avoided: {est.cost_avoided:,.2f}  (returns cost {est.total_return_cost:,.2f} in all)")
    print("  An estimate, not a promise: it assumes every flagged order that came back would have been stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path, help="train from this import file instead of the database")
    parser.add_argument("--save", action="store_true", help="store the result in the database")
    parser.add_argument("--shipping-cost", type=float, help="print the savings estimate for this cost per parcel")
    parser.add_argument("--flag", default="High", help="levels that count as flagged in the estimate, e.g. High or High,Medium")
    args = parser.parse_args()
    if args.csv and args.save:
        raise SystemExit("--save needs the database; it cannot be used with --csv.")

    if args.csv:
        orders = read_csv(args.csv)
    else:
        from sqlalchemy.orm import Session

        from app.db.session import get_engine
        from app.services.order_risk_data import load_order_inputs

        with Session(get_engine()) as db:
            orders = load_order_inputs(db)

    print(f"{len(orders):,} orders loaded")
    result = train_order_risk(orders)
    print_report(result)
    if args.shipping_cost is not None:
        estimate = savings_estimate(result, orders, args.shipping_cost, tuple(args.flag.split(",")))
        if estimate is None:
            print()
            print("No savings estimate: the model is not available, so there is nothing to estimate.")
        else:
            print_savings(estimate)

    if args.save:
        from app.services.order_risk_runs import save_run

        with Session(get_engine()) as db:
            run = save_run(db, result)
            print(f"Saved as run {run.id}")


if __name__ == "__main__":
    main()
