"""Turn on row-level security for every application table.

Hosts such as Supabase expose tables in the `public` schema through an automatic REST
API that anyone holding the project's public key can call. With row-level security
switched on and no policies, those API roles can read and write nothing. The app is
unaffected: it connects as the table owner, which bypasses row-level security. On a
plain PostgreSQL server this changes nothing for the app either.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("users", "sessions", "customers", "orders", "import_jobs")


def upgrade() -> None:
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
