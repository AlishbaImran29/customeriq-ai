"""Cash Tracker endpoints: COD money couriers owe, courier payments (import and manual), demo clean-up."""

from fastapi import APIRouter, Depends, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.v1.shipments import _read_limited
from app.db.session import get_db
from app.models import CourierPayment
from app.models.shipment import SOURCE_DEMO
from app.schemas.cash import (
    BucketOut, CourierCashOut, PaymentImportOut, PaymentIn, PaymentSavedOut, PaymentsSummaryOut, PendingRowOut, TrackerOut,
)
from app.schemas.shipments import DemoDeleteOut
from app.services.cash_tracker import CourierCash, compute_tracker, pending_list
from app.services.import_files import file_type_of
from app.services.payment_import import MAX_STORED_ERRORS, add_payment, import_payments

router = APIRouter(prefix="/cash", tags=["cash"])


def _courier(c: CourierCash) -> CourierCashOut:
    return CourierCashOut(
        courier=c.courier, delivered_cod=float(c.delivered_cod), received=float(c.received), pending=float(c.pending),
        unpaid_parcels=c.unpaid_parcels, paid_parcels=c.paid_parcels, oldest_pending_days=c.oldest_pending_days,
        average_days_to_pay=c.average_days_to_pay, enough=c.enough, needed=c.needed, credit=float(c.credit),
        overdue_amount=float(c.overdue_amount), overdue_parcels=c.overdue_parcels,
    )


@router.get("/tracker", response_model=TrackerOut, summary="COD money couriers owe")
def tracker(
    alert_days: int | None = Query(None, ge=1, le=365, description="Flag money unpaid for more than this many days"),
    source: str = Query("auto", pattern="^(auto|real|demo)$"),
    db: Session = Depends(get_db),
) -> TrackerOut:
    t = compute_tracker(db, alert_days=alert_days, source=source)
    return TrackerOut(
        as_of=t.as_of, alert_days=t.alert_days, source_used=t.source_used, real_cod_parcels=t.real_cod_parcels,
        demo_cod_parcels=t.demo_cod_parcels, payments=t.payments, min_group_count=t.min_group_count,
        delivered_cod=float(t.delivered_cod), received=float(t.received), pending=float(t.pending), credit=float(t.credit),
        unpaid_parcels=t.unpaid_parcels, oldest_pending_days=t.oldest_pending_days,
        couriers=[_courier(c) for c in t.couriers],
        buckets=[BucketOut(label=b.label, parcels=b.parcels, amount=float(b.amount)) for b in t.buckets],
        alerts=[_courier(c) for c in t.alerts],
    )


@router.get("/pending", response_model=list[PendingRowOut], summary="Unpaid COD parcels, oldest first")
def pending(source: str = Query("auto", pattern="^(auto|real|demo)$"), db: Session = Depends(get_db)) -> list[PendingRowOut]:
    return [
        PendingRowOut(
            courier=r.courier, city=r.city, reference=r.reference, delivered_on=r.delivered_on, days_pending=r.days_pending,
            cod_amount=float(r.cod_amount), paid=float(r.paid), still_owed=float(r.still_owed), status=r.status,
        )
        for r in pending_list(db, source=source)
    ]


@router.post("/payments/import", response_model=PaymentImportOut, status_code=status.HTTP_201_CREATED, summary="Import courier payments from a CSV or Excel file")
async def import_file(file: UploadFile, db: Session = Depends(get_db)) -> PaymentImportOut:
    file_type = file_type_of((file.filename or "payments")[:255])
    content = await _read_limited(file)
    result = await run_in_threadpool(import_payments, db, content, file_type)
    return PaymentImportOut(
        rows_in_file=result.rows_in_file, created=result.created, updated=result.updated, rejected=result.rejected,
        new_courier_names=result.new_courier_names, error_count=result.error_count, errors=result.errors,
        errors_truncated=result.error_count > MAX_STORED_ERRORS,
    )


@router.post("/payments", response_model=PaymentSavedOut, status_code=status.HTTP_201_CREATED, summary="Add one courier payment by hand")
def add_one(body: PaymentIn, db: Session = Depends(get_db)) -> PaymentSavedOut:
    from decimal import Decimal

    row = add_payment(db, body.courier_name, body.payment_date, Decimal(str(body.amount)), body.reference, body.order_ids)
    return PaymentSavedOut(courier=row.courier.name, payment_date=row.payment_date, amount=float(row.amount))


@router.get("/payments/summary", response_model=PaymentsSummaryOut, summary="How many payments are saved")
def payments_summary(db: Session = Depends(get_db)) -> PaymentsSummaryOut:
    total = db.scalar(select(func.count()).select_from(CourierPayment)) or 0
    demo = db.scalar(select(func.count()).select_from(CourierPayment).where(CourierPayment.source == SOURCE_DEMO)) or 0
    return PaymentsSummaryOut(payments=int(total), demo_payments=int(demo))


@router.delete("/payments/demo", response_model=DemoDeleteOut, summary="Delete the made-up demo payments")
def delete_demo(db: Session = Depends(get_db)) -> DemoDeleteOut:
    """Only payments marked as demo data; real payments are never touched."""
    deleted = db.execute(delete(CourierPayment).where(CourierPayment.source == SOURCE_DEMO)).rowcount or 0
    db.commit()
    return DemoDeleteOut(deleted=int(deleted))
