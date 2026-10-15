import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db, get_engine
from app.main import app

requires_database = pytest.mark.skipif(
    not get_settings().database_configured,
    reason="Database not configured in backend/.env",
)


@pytest.fixture
def db_session():
    """A session on empty tables whose work is always rolled back.

    Each commit only releases a SAVEPOINT inside an outer transaction, so tests
    never change the real database, and existing data cannot affect results.
    """
    connection = get_engine().connect()
    outer = connection.begin()
    # Start every test from empty tables. This is part of the outer transaction,
    # so the real data reappears when it is rolled back.
    connection.execute(text("DELETE FROM orders"))
    connection.execute(text("DELETE FROM customers"))
    connection.execute(text("DELETE FROM import_jobs"))
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def db_client(db_session):
    """API client whose requests use the rolled-back test session."""
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
