import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ImportStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ImportJob(TimestampMixin, Base):
    """Tracks one uploaded file and the outcome of processing it."""

    __tablename__ = "import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(10))
    # Detected layout: "standard" columns or a store export such as "shopify".
    file_format: Mapped[str] = mapped_column(String(20), default="standard", server_default="standard")
    # Non-empty data rows in the file (Shopify: one per line item, grouped into orders).
    rows_in_file: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[ImportStatus] = mapped_column(
        Enum(
            ImportStatus,
            name="import_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=ImportStatus.PENDING,
    )
    rows_received: Mapped[int] = mapped_column(Integer, default=0)
    # New orders inserted by this import.
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    # Existing orders (same order_id) overwritten with this file's values.
    rows_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    # Total problems found; `errors` stores only the first ones (see MAX_STORED_ERRORS).
    error_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Row-level problems as [{"row", "column", "message"}]. Messages describe the
    # problem only and must not copy customer values (emails, names, amounts).
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
