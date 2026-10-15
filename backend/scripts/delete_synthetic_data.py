"""Delete test data (made-up or public datasets) from the database.

Only rows from the chosen test source are touched; your own data is never deleted:
- synthetic (default): IDs starting with "SYN-", made by scripts/generate_demo_data.py
- public: IDs starting with "PUB-", made by scripts/convert_uci_online_retail.py
Matching import records are removed too once they have no orders left.

Usage (from backend/):
    .venv/Scripts/python.exe scripts/delete_synthetic_data.py --dry-run          # counts only
    .venv/Scripts/python.exe scripts/delete_synthetic_data.py                    # type DELETE
    .venv/Scripts/python.exe scripts/delete_synthetic_data.py --source public    # the UCI data
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import get_engine  # noqa: E402
from app.models import Customer, ImportJob, Order  # noqa: E402

SOURCES = {
    "synthetic": ("SYN-%", "demo_orders_synthetic.csv"),
    "public": ("PUB-%", "public_uci_online_retail_ii.csv"),
}
PREFIX, SYNTHETIC_FILE = SOURCES["synthetic"]  # defaults, used when no source is given


def counts(db: Session, prefix: str = PREFIX, filename: str = SYNTHETIC_FILE) -> dict[str, int]:
    orphan_jobs = (
        select(ImportJob.id)
        .where(ImportJob.filename == filename)
        .where(~ImportJob.id.in_(
            select(Order.import_job_id)
            .where(Order.import_job_id.is_not(None))
            .where(~Order.external_id.like(prefix))
        ))
    )
    return {
        "orders": db.scalar(select(func.count()).select_from(Order).where(Order.external_id.like(prefix))) or 0,
        "customers": db.scalar(select(func.count()).select_from(Customer).where(Customer.external_id.like(prefix))) or 0,
        "import_jobs": db.scalar(select(func.count()).select_from(orphan_jobs.subquery())) or 0,
        "real_customers_kept": db.scalar(
            select(func.count()).select_from(Customer).where(~Customer.external_id.like(prefix))
        ) or 0,
    }


def delete_synthetic(db: Session, prefix: str = PREFIX, filename: str = SYNTHETIC_FILE) -> None:
    db.execute(delete(Order).where(Order.external_id.like(prefix)))
    # Only customers who have no real orders left (all of theirs were synthetic).
    db.execute(
        delete(Customer)
        .where(Customer.external_id.like(prefix))
        .where(~Customer.id.in_(select(Order.customer_id)))
    )
    db.execute(
        delete(ImportJob)
        .where(ImportJob.filename == filename)
        .where(~ImportJob.id.in_(
            select(Order.import_job_id).where(Order.import_job_id.is_not(None))
        ))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=sorted(SOURCES), default="synthetic",
                        help="which test data to remove (default: synthetic)")
    parser.add_argument("--dry-run", action="store_true", help="only show what would be deleted")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args()

    prefix, filename = SOURCES[args.source]
    with Session(get_engine()) as db:
        found = counts(db, prefix, filename)
        print(
            f"{args.source.capitalize()} test data found: {found['customers']} customers, {found['orders']} orders, "
            f"{found['import_jobs']} import record(s). Real customers kept: {found['real_customers_kept']}."
        )
        if found["orders"] == 0 and found["customers"] == 0 and found["import_jobs"] == 0:
            print("Nothing to delete.")
            return 0
        if args.dry_run:
            print("Dry run: nothing was deleted.")
            return 0
        if not args.yes and input(f'Type DELETE to remove the {args.source} test data: ').strip() != "DELETE":
            print("Cancelled: nothing was deleted.")
            return 1
        delete_synthetic(db, prefix, filename)
        db.commit()
        left = counts(db, prefix, filename)
        print(f"Done. Remaining {args.source} test data: {left['customers']} customers, {left['orders']} orders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
