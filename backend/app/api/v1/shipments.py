"""Shipments: the parcels handed to couriers (import, summary, and removing demo data)."""

from fastapi import APIRouter, Depends, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.models import Shipment
from app.models.shipment import SOURCE_DEMO
from app.schemas.shipments import DemoDeleteOut, ShipmentImportOut, ShipmentSummaryOut
from app.services.import_files import file_type_of
from app.services.names import CITY_NAMES, COURIERS
from app.services.shipment_import import MAX_STORED_ERRORS, import_shipments

# Vercel accepts request bodies of at most 4.5 MB.
MAX_FILE_BYTES = 4 * 1024 * 1024
_CHUNK = 1024 * 1024

router = APIRouter(prefix="/shipments", tags=["shipments"])


async def _read_limited(file: UploadFile) -> bytes:
    data = bytearray()
    while chunk := await file.read(_CHUNK):
        data.extend(chunk)
        if len(data) > MAX_FILE_BYTES:
            raise ApiError(413, "file_too_large", "The file is larger than 4 MB. Split it and upload the parts.")
    return bytes(data)


@router.post("/import", response_model=ShipmentImportOut, status_code=status.HTTP_201_CREATED, summary="Import shipments from a CSV or Excel file")
async def import_file(file: UploadFile, db: Session = Depends(get_db)) -> ShipmentImportOut:
    """Valid rows are saved (or updated when imported before); invalid rows are rejected and listed."""
    file_type = file_type_of((file.filename or "shipments")[:255])
    content = await _read_limited(file)
    result = await run_in_threadpool(import_shipments, db, content, file_type)
    return ShipmentImportOut(
        rows_in_file=result.rows_in_file, created=result.created, updated=result.updated, rejected=result.rejected,
        linked_to_orders=result.linked_to_orders, unlinked=result.unlinked, orders_updated=result.orders_updated,
        new_courier_names=result.new_courier_names, new_city_names=result.new_city_names,
        error_count=result.error_count, errors=result.errors, errors_truncated=result.error_count > MAX_STORED_ERRORS,
    )


@router.get("/summary", response_model=ShipmentSummaryOut, summary="How many shipments are saved, and the names in use")
def summary(db: Session = Depends(get_db)) -> ShipmentSummaryOut:
    total = db.scalar(select(func.count()).select_from(Shipment)) or 0
    linked = db.scalar(select(func.count()).select_from(Shipment).where(Shipment.order_id.is_not(None))) or 0
    demo = db.scalar(select(func.count()).select_from(Shipment).where(Shipment.source == SOURCE_DEMO)) or 0
    used_couriers = set(db.scalars(select(Shipment.courier).distinct()))
    used_cities = set(db.scalars(select(Shipment.city).where(Shipment.city.is_not(None)).distinct()))
    return ShipmentSummaryOut(
        shipments=int(total), linked_to_orders=int(linked), demo_shipments=int(demo),
        couriers=sorted(set(COURIERS.names) | used_couriers), cities=sorted(set(CITY_NAMES.names) | used_cities),
    )


@router.delete("/demo", response_model=DemoDeleteOut, summary="Delete the made-up demo shipments")
def delete_demo(db: Session = Depends(get_db)) -> DemoDeleteOut:
    """Only shipments marked as demo data; real shipments are never touched."""
    deleted = db.execute(delete(Shipment).where(Shipment.source == SOURCE_DEMO)).rowcount or 0
    db.commit()
    return DemoDeleteOut(deleted=int(deleted))
