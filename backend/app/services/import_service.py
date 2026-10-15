"""Save validated import rows to PostgreSQL and record the outcome in import_jobs.

Policy (agreed for Phase 2):
- Valid rows are imported; invalid rows are rejected and reported.
- An order_id that already exists is updated with the new file's values.
- Customers are matched by customer_id; blank optional fields keep old values.
"""

import logging
import uuid
from datetime import UTC, datetime
from pathlib import PurePath

from sqlalchemy import func, literal_column
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Customer, ImportJob, ImportStatus, Order
from app.services.import_files import parse_file
from app.services.import_validation import OrderRow, validate_rows

logger = logging.getLogger(__name__)

MAX_STORED_ERRORS = 200
_BATCH_SIZE = 1000


def safe_filename(filename: str | None) -> str:
    name = PurePath((filename or "upload").replace("\\", "/")).name
    return (name or "upload")[:255]


def run_import(db: Session, filename: str, file_type: str, content: bytes) -> ImportJob:
    """Validate and import a file. File-level problems raise ApiError (no job saved)."""
    parsed = parse_file(content, file_type)
    result = validate_rows(parsed)

    job = ImportJob(
        id=uuid.uuid4(),
        filename=filename,
        file_type=file_type,
        status=ImportStatus.PROCESSING,
        rows_received=len(parsed.rows),
        rows_imported=0,
        rows_updated=0,
        rows_rejected=result.rejected_rows,
        error_count=len(result.errors),
        errors=[e.as_dict() for e in result.errors[:MAX_STORED_ERRORS]],
    )
    db.add(job)
    db.commit()

    try:
        inserted, updated = _save_rows(db, job.id, result.rows)
        job.rows_imported = inserted
        job.rows_updated = updated
        job.status = ImportStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Import %s failed while saving rows", job.id)
        job.status = ImportStatus.FAILED
        job.rows_imported = 0
        job.rows_updated = 0
        job.completed_at = datetime.now(UTC)
        db.commit()
        raise

    # Counts only — never log file contents or customer values.
    logger.info(
        "Import %s completed: received=%d inserted=%d updated=%d rejected=%d",
        job.id, job.rows_received, job.rows_imported, job.rows_updated, job.rows_rejected,
    )
    return job


def _save_rows(db: Session, job_id: uuid.UUID, rows: list[OrderRow]) -> tuple[int, int]:
    """Upsert customers then orders in one transaction. Returns (inserted, updated)."""
    if not rows:
        return 0, 0

    # Last row wins for each customer's details within a file.
    customers: dict[str, OrderRow] = {}
    for row in rows:
        customers[row.customer_id] = row

    customer_ids: dict[str, int] = {}
    customer_values = [
        {
            "external_id": r.customer_id,
            "email": r.email,
            "first_name": r.first_name,
            "last_name": r.last_name,
            "country": r.country,
        }
        for r in customers.values()
    ]
    for batch in _batches(customer_values):
        stmt = insert(Customer).values(batch)
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=[Customer.external_id],
            set_={
                "email": excluded.email,
                "first_name": func.coalesce(excluded.first_name, Customer.first_name),
                "last_name": func.coalesce(excluded.last_name, Customer.last_name),
                "country": func.coalesce(excluded.country, Customer.country),
                "updated_at": func.now(),
            },
        ).returning(Customer.id, Customer.external_id)
        customer_ids.update({ext: cid for cid, ext in db.execute(stmt)})

    inserted = updated = 0
    order_values = [
        {
            "external_id": r.order_id,
            "customer_id": customer_ids[r.customer_id],
            "order_date": r.order_date,
            "order_value": r.order_value,
            "product_category": r.product_category,
            "channel": r.channel,
            "engagement_score": r.engagement,
            "import_job_id": job_id,
        }
        for r in rows
    ]
    for batch in _batches(order_values):
        stmt = insert(Order).values(batch)
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=[Order.external_id],
            set_={
                "customer_id": excluded.customer_id,
                "order_date": excluded.order_date,
                "order_value": excluded.order_value,
                "product_category": func.coalesce(
                    excluded.product_category, Order.product_category
                ),
                "channel": func.coalesce(excluded.channel, Order.channel),
                "engagement_score": func.coalesce(
                    excluded.engagement_score, Order.engagement_score
                ),
                "import_job_id": excluded.import_job_id,
                "updated_at": func.now(),
            },
        # PostgreSQL sets xmax = 0 only for freshly inserted rows.
        ).returning(literal_column("(xmax = 0)").label("inserted"))
        for (was_inserted,) in db.execute(stmt):
            if was_inserted:
                inserted += 1
            else:
                updated += 1
    return inserted, updated


def _batches(items: list[dict], size: int = _BATCH_SIZE):
    for start in range(0, len(items), size):
        yield items[start : start + size]
