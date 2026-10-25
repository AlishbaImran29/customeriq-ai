"""Roles (owner, staff, viewer) on users, and the action log.

The oldest existing account becomes the owner; every other existing account becomes a viewer (the owner can raise them).

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(length=10), server_default="viewer", nullable=False))
    op.create_check_constraint("ck_users_user_role_known", "users", "role IN ('owner', 'staff', 'viewer')")
    op.execute("UPDATE users SET role = 'owner' WHERE id = (SELECT id FROM users ORDER BY created_at, id LIMIT 1)")
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor_email", sa.String(length=320), nullable=False),
        sa.Column("actor_role", sa.String(length=10), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("route", sa.String(length=200), nullable=False),
        sa.Column("outcome", sa.String(length=10), nullable=False),
        sa.Column("detail", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index("ix_audit_log_at", "audit_log", ["at"])
    op.create_index("ix_audit_log_actor", "audit_log", ["actor_email"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_actor", table_name="audit_log")
    op.drop_index("ix_audit_log_at", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_constraint("ck_users_user_role_known", "users", type_="check")
    op.drop_column("users", "role")
