import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.models import ImportStatus


class CamelModel(BaseModel):
    """Serialises fields as camelCase to match the TypeScript frontend."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, from_attributes=True
    )


class ImportRowError(CamelModel):
    row: int | None
    column: str | None
    message: str


class ImportJobOut(CamelModel):
    id: uuid.UUID
    filename: str
    file_type: str
    file_format: str
    rows_in_file: int
    status: ImportStatus
    rows_received: int
    rows_imported: int
    rows_updated: int
    rows_rejected: int
    error_count: int
    errors: list[ImportRowError]
    errors_truncated: bool
    created_at: datetime
    completed_at: datetime | None


class ImportJobSummary(CamelModel):
    """List view without the per-row error details."""

    id: uuid.UUID
    filename: str
    file_type: str
    file_format: str
    rows_in_file: int
    status: ImportStatus
    rows_received: int
    rows_imported: int
    rows_updated: int
    rows_rejected: int
    error_count: int
    created_at: datetime
    completed_at: datetime | None
