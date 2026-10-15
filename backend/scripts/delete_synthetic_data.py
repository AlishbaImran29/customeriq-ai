"""Delete the SYNTHETIC demo data (IDs starting with "SYN-") from the database.

Only rows created by scripts/generate_demo_data.py are touched: customers and
orders whose IDs start with "SYN-", plus import records for the synthetic file
that no longer have any orders. Real data is never deleted.

Usage (from backend/):
    .venv/Scripts/python.exe scripts/delete_synthetic_data.py --dry-run   # show counts only
    .venv/Scripts/python.exe scripts/delete_synthetic_data.py             # asks you to type DELETE
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import get_engine  # noqa: E402
from app.models import Customer, ImportJob, Order  # noqa: E402

PREFIX = "SYN-%"
SYNTHETIC_FILE = "demo_orders_synthetic.csv"


def counts(db: Session) -> dict[str, int]:
    orphan_jobs = (
        select(ImportJob.id)
        .where(ImportJob.filename == SYNTHETIC_FILE)
        .where(~ImportJob.id.in_(
            select(Order.import_job_id)
            .where(Order.import_job_id.is_not(None))
            .where(~Order.external_id.like(PREFIX))
        ))
    )
    return {
        "orders": db.scalar(select(func.count()).select_from(Order).where(Order.external_id.like(PREFIX))) or 0,
        "customers": db.scalar(select(func.count()).select_from(Customer).where(Customer.external_id.like(PREFIX))) or 0,
        "import_jobs": db.scalar(select(func.count()).select_from(orphan_jobs.subquery())) or 0,
        "real_customers_kept": db.scalar(
            select(func.count()).select_from(Customer).where(~Customer.external_id.like(PREFIX))
        ) or 0,
    }


def delete_synthetic(db: Session) -> None:
    db.execute(delete(Order).where(Order.external_id.like(PREFIX)))
    # Only customers who have no real orders left (all of theirs were synthetic).
    db.execute(
        delete(Customer)
        .where(Customer.external_id.like(PREFIX))
        .where(~Customer.id.in_(select(Order.customer_id)))
    )
    db.execute(
        delete(ImportJob)
        .where(ImportJob.filename == SYNTHETIC_FILE)
        .where(~ImportJob.id.in_(
            select(Order.import_job_id).where(Order.import_job_id.is_not(None))
        ))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="only show what would be deleted")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args()

    with Session(get_engine()) as db:
        found = counts(db)
        print(
            f"Synthetic data found: {found['customers']} customers, {found['orders']} orders, "
            f"{found['import_jobs']} import record(s). Real customers kept: {found['real_customers_kept']}."
        )
        if found["orders"] == 0 and found["customers"] == 0 and found["import_jobs"] == 0:
            print("Nothing to delete.")
            return 0
        if args.dry_run:
            print("Dry run: nothing was deleted.")
            return 0
        if not args.yes and input('Type DELETE to remove the synthetic data: ').strip() != "DELETE":
            print("Cancelled: nothing was deleted.")
            return 1
        delete_synthetic(db)
        db.commit()
        left = counts(db)
        print(f"Done. Remaining synthetic: {left['customers']} customers, {left['orders']} orders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
