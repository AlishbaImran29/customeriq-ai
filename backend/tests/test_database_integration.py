"""Checks against the real PostgreSQL database configured in backend/.env.

Skipped automatically when the database is not configured.
"""

import pytest
from sqlalchemy import inspect

from app.core.config import get_settings
from app.db.session import check_database, get_engine

pytestmark = pytest.mark.skipif(
    not get_settings().database_configured,
    reason="Database not configured in backend/.env",
)


def test_database_is_reachable():
    assert check_database() == "ok"


def test_migrations_created_expected_tables():
    tables = set(inspect(get_engine()).get_table_names())
    assert {"customers", "orders", "import_jobs", "alembic_version"} <= tables
