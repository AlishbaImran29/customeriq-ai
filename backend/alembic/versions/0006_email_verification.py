"""Email verification: remember who proved their address, and the pending code.

Accounts that already exist are marked as verified (they have been signing in already), so
nobody is locked out by this change.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("verify_code_hash", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("verify_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("verify_attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("verify_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("verify_send_count", sa.Integer(), server_default="0", nullable=False))
    op.execute("UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL")


def downgrade() -> None:
    for column in (
        "verify_send_count", "verify_sent_at", "verify_attempts", "verify_expires_at",
        "verify_code_hash", "email_verified_at",
    ):
        op.drop_column("users", column)
