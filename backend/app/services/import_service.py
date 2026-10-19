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
from app.services.customer_identity import assign_customers_by_phone, existing_phone_owners
from app.services.import_files import parse_file
from app.services.import_formats import convert
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
    converted = convert(parsed)  # e.g. Shopify line items -> one row per order
    result = validate_rows(converted.parsed)
    problems = sorted(converted.skipped + result.errors, key=lambda e: e.row or 0)

    job = ImportJob(
        id=uuid.uuid4(),
        filename=filename,
        file_type=file_type,
        file_format=converted.file_format,
        rows_in_file=len(parsed.rows),
        status=ImportStatus.PROCESSING,
        rows_received=len(converted.parsed.rows) + len(converted.skipped),
        rows_imported=0,
        rows_updated=0,
        rows_rejected=result.rejected_rows + len(converted.skipped),
        error_count=len(problems),
        errors=[e.as_dict() for e in problems[:MAX_STORED_ERRORS]],
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
        "Import %s (%s) completed: received=%d inserted=%d updated=%d rejected=%d",
        job.id, job.file_format, job.rows_received, job.rows_imported, job.rows_updated,
        job.rows_rejected,
    )
    return job


def _save_rows(db: Session, job_id: uuid.UUID, rows: list[OrderRow]) -> tuple[int, int]:
    """Upsert customers then orders in one transaction. Returns (inserted, updated)."""
    if not rows:
        return 0, 0

    # A phone number is the key that merges repeat customers: a row whose number already belongs
    # to a customer (saved earlier, or seen earlier in this file) is added to THAT customer.
    owners = existing_phone_owners(db, {r.phone_normalised for r in rows if r.phone_normalised})
    rows, merged = assign_customers_by_phone(rows, owners)
    if merged:
        logger.info("Merged %d rows into customers that already had the same phone number", merged)

    # Last row wins for each customer's details within a file, except these fields: they use the
    # last row that HAS a value, so a later row without an email or a name cannot hide an earlier one.
    customers: dict[str, OrderRow] = {}
    contact: dict[str, dict[str, str]] = {}
    for row in rows:
        customers[row.customer_id] = row
        found = contact.setdefault(row.customer_id, {})
        for field in ("email", "phone", "phone_normalised", "first_name", "last_name", "country"):
            if getattr(row, field):
                found[field] = getattr(row, field)

    customer_ids: dict[str, int] = {}
    customer_values = [
        {
            "external_id": r.customer_id,
            "email": contact[r.customer_id].get("email"),
            "first_name": contact[r.customer_id].get("first_name"),
            "last_name": contact[r.customer_id].get("last_name"),
            "country": contact[r.customer_id].get("country"),
            "phone": contact[r.customer_id].get("phone"),
            "phone_normalised": contact[r.customer_id].get("phone_normalised"),
        }
        for r in customers.values()
    ]
    for batch in _batches(customer_values):
        stmt = insert(Customer).values(batch)
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=[Customer.external_id],
            set_={
                "email": func.coalesce(excluded.email, Customer.email),
                "first_name": func.coalesce(excluded.first_name, Customer.first_name),
                "last_name": func.coalesce(excluded.last_name, Customer.last_name),
                "country": func.coalesce(excluded.country, Customer.country),
                "phone": func.coalesce(excluded.phone, Customer.phone),
                # A customer keeps the number they already have; a new one is only filled in.
                "phone_normalised": func.coalesce(Customer.phone_normalised, excluded.phone_normalised),
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
            "sales_channel": r.sales_channel or "other",
            "city": r.city,
            "products": r.products,
            "payment_type": r.payment_type,
            "note": r.note,
            "engagement_score": r.engagement,
            "ordered_at": r.ordered_at,
            "item_count": r.item_count,
            "distinct_products": r.distinct_products,
            "outcome": r.outcome,
            "outcome_date": r.outcome_date,
            "label_source": r.label_source,
            "address_length": r.address_length,
            "has_house_number": r.has_house_number,
            "phone_valid": r.phone_valid,
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
                # "other" means "the file did not say": keep the channel that is already saved.
                "sales_channel": func.coalesce(func.nullif(excluded.sales_channel, "other"), Order.sales_channel),
                "city": func.coalesce(excluded.city, Order.city),
                "products": func.coalesce(excluded.products, Order.products),
                "payment_type": func.coalesce(excluded.payment_type, Order.payment_type),
                "note": func.coalesce(excluded.note, Order.note),
                "engagement_score": func.coalesce(
                    excluded.engagement_score, Order.engagement_score
                ),
                # Order Risk facts: a file that leaves them blank keeps what is already saved
                # (so re-importing plain orders never erases a courier outcome).
                "ordered_at": func.coalesce(excluded.ordered_at, Order.ordered_at),
                "item_count": func.coalesce(excluded.item_count, Order.item_count),
                "distinct_products": func.coalesce(excluded.distinct_products, Order.distinct_products),
                "outcome": func.coalesce(excluded.outcome, Order.outcome),
                "outcome_date": func.coalesce(excluded.outcome_date, Order.outcome_date),
                "label_source": func.coalesce(excluded.label_source, Order.label_source),
                "address_length": func.coalesce(excluded.address_length, Order.address_length),
                "has_house_number": func.coalesce(excluded.has_house_number, Order.has_house_number),
                "phone_valid": func.coalesce(excluded.phone_valid, Order.phone_valid),
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
