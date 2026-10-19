import uuid

from fastapi import APIRouter, Depends, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.models import ImportJob
from app.schemas.imports import CourierImportOut, ImportJobOut, ImportJobSummary
from app.services.courier_import import MAX_STORED_ERRORS, run_courier_import
from app.services.import_files import MAX_FILE_BYTES, file_type_of
from app.services.import_service import run_import, safe_filename

router = APIRouter(prefix="/imports", tags=["imports"])

_CHUNK = 1024 * 1024


def _job_out(job: ImportJob) -> ImportJobOut:
    return ImportJobOut.model_validate(
        {
            **{c: getattr(job, c) for c in ImportJobOut.model_fields if hasattr(job, c)},
            "errors_truncated": job.error_count > len(job.errors),
        }
    )


async def _read_limited(file: UploadFile) -> bytes:
    """Read the upload, stopping as soon as it exceeds the size limit."""
    data = bytearray()
    while chunk := await file.read(_CHUNK):
        data.extend(chunk)
        if len(data) > MAX_FILE_BYTES:
            raise ApiError(
                413,
                "file_too_large",
                f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.",
            )
    return bytes(data)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ImportJobOut,
    summary="Upload a CSV or XLSX file of customer orders",
)
async def create_import(file: UploadFile, db: Session = Depends(get_db)) -> ImportJobOut:
    """Validate the file on the server, import valid rows, and report rejected ones.

    File-level problems (wrong type, too large, empty, missing columns) return an
    error and nothing is saved. Otherwise an import job is created: valid rows are
    imported, existing order_ids are updated, and invalid rows are listed in `errors`.
    """
    filename = safe_filename(file.filename)
    file_type = file_type_of(filename)
    content = await _read_limited(file)
    # Parsing and database work are blocking; keep them off the event loop.
    job = await run_in_threadpool(run_import, db, filename, file_type, content)
    return _job_out(job)


@router.post(
    "/courier",
    response_model=CourierImportOut,
    summary="Upload a courier status file (delivered / returned per order)",
)
async def create_courier_import(file: UploadFile, db: Session = Depends(get_db)) -> CourierImportOut:
    """Add the real delivery result to orders that are already imported.

    Columns: order_id, customer_id, status (delivered or returned), date. Each matching
    order is labelled with `label_source = courier data`. Rows that do not match an order
    are rejected and listed; nothing else is changed.
    """
    filename = safe_filename(file.filename)
    file_type = file_type_of(filename)
    content = await _read_limited(file)
    result = await run_in_threadpool(run_courier_import, db, content, file_type)
    return CourierImportOut.model_validate(
        {**result.__dict__, "errors_truncated": result.error_count > MAX_STORED_ERRORS}
    )


@router.get("", response_model=list[ImportJobSummary], summary="List recent imports")
def list_imports(
    limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)
) -> list[ImportJob]:
    return list(
        db.scalars(select(ImportJob).order_by(ImportJob.created_at.desc()).limit(limit))
    )


@router.get("/{import_id}", response_model=ImportJobOut, summary="Get one import")
def get_import(import_id: uuid.UUID, db: Session = Depends(get_db)) -> ImportJobOut:
    job = db.get(ImportJob, import_id)
    if job is None:
        raise ApiError(404, "import_not_found", "No import exists with this id.")
    return _job_out(job)
