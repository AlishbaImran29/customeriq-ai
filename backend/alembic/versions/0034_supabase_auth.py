"""Sign-in moves to Supabase Auth (email + password, no email-confirmation step).

Accounts and passwords now live in Supabase, so the old password, email-code and session storage is removed. The old accounts are
removed too (their passwords cannot be moved): sign up again with Supabase; the first account becomes the owner.

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("sessions")
    op.execute("DELETE FROM users")
    for column in ("password_hash", "email_verified_at", "verify_code_hash", "verify_expires_at", "verify_attempts", "verify_sent_at", "verify_send_count"):
        op.drop_column("users", column)


def downgrade() -> None:
    op.add_column("users", sa.Column("verify_send_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("verify_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("verify_attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("verify_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("verify_code_hash", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), server_default="", nullable=False))
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
    )
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
