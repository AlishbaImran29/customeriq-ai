"""Add rows_updated and error_count to import_jobs.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "import_jobs",
        sa.Column("rows_updated", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "import_jobs",
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("import_jobs", "error_count")
    op.drop_column("import_jobs", "rows_updated")
