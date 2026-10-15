import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import require_user
from app.core.config import get_settings
from app.db.session import get_db, get_engine
from app.main import app
from app.services.auth import reset_login_limits

requires_database = pytest.mark.skipif(
    not get_settings().database_configured,
    reason="Database not configured in backend/.env",
)


@pytest.fixture(autouse=True)
def signed_in_test_user(request):
    """Most tests are about data, not sign-in: they run as an always-signed-in test user.
    Tests marked `real_auth` use the real sign-in flow instead."""
    reset_login_limits()
    if request.node.get_closest_marker("real_auth"):
        yield
        return
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), email="test@example.com", name="Test User"
    )
    yield
    app.dependency_overrides.pop(require_user, None)


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
    connection.execute(text("DELETE FROM sessions"))
    connection.execute(text("DELETE FROM users"))
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
