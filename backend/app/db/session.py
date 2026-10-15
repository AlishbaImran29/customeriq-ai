"""Database engine and session handling.

The engine is created lazily, so the API (and its tests) can start even when
the database is not configured yet; endpoints that need it report the problem.
"""

import logging
from collections.abc import Iterator
from functools import lru_cache
from typing import Literal

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DatabaseStatus = Literal["ok", "not_configured", "unavailable"]


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.sqlalchemy_url(),
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_args={"connect_timeout": 5},
    )


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a session and always closes it."""
    session = sessionmaker(bind=get_engine(), expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def check_database() -> DatabaseStatus:
    """Return "ok", "not_configured", or "unavailable". Never raises."""
    if not get_settings().database_configured:
        return "not_configured"
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        # Driver messages name the host/user but never include the password.
        logger.warning("Database check failed: %s: %s", type(exc).__name__, exc)
        return "unavailable"
