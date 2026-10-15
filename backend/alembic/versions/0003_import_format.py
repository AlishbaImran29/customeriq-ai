"""Add file_format and rows_in_file to import_jobs.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "import_jobs",
        sa.Column("file_format", sa.String(length=20), server_default="standard", nullable=False),
    )
    op.add_column(
        "import_jobs",
        sa.Column("rows_in_file", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("import_jobs", "rows_in_file")
    op.drop_column("import_jobs", "file_format")
