import pytest
from fastapi.testclient import TestClient
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
    """A session whose work is always rolled back, even after session.commit().

    Each commit only releases a SAVEPOINT inside an outer transaction, so tests
    never leave data in the real database.
    """
    connection = get_engine().connect()
    outer = connection.begin()
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
