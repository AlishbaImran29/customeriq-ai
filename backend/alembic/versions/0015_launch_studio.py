"""Launch Studio, step 1: launch projects, uploaded Google Trends files, and an AI answer cache.

New tables only, so nothing that exists changes.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_now = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "launch_projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=12), server_default="idea", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("launched_on", sa.Date(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_launch_projects"),
        sa.CheckConstraint("status IN ('idea', 'sourcing', 'ready', 'launched', 'dropped')", name="ck_launch_projects_launch_status_known"),
    )
    op.create_table(
        "trend_uploads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("launch_project_id", sa.Integer(), nullable=True),
        sa.Column("keyword", sa.String(length=120), nullable=False),
        sa.Column("region", sa.String(length=60), nullable=True),
        sa.Column("granularity", sa.String(length=8), nullable=True),
        sa.Column("points", postgresql.JSONB(), nullable=True),
        sa.Column("related", postgresql.JSONB(), nullable=True),
        sa.Column("label", sa.String(length=12), nullable=True),
        sa.Column("ratio", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_trend_uploads"),
        sa.ForeignKeyConstraint(["launch_project_id"], ["launch_projects.id"], name="fk_trend_uploads_launch_project_id_launch_projects", ondelete="CASCADE"),
    )
    op.create_index("ix_trend_uploads_launch_project_id", "trend_uploads", ["launch_project_id"])
    op.create_table(
        "ai_cache",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_ai_cache"),
    )
    # Same protection as every other table (see 0005).
    for table in ("launch_projects", "trend_uploads", "ai_cache"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("ai_cache")
    op.drop_table("trend_uploads")
    op.drop_table("launch_projects")
