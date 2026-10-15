"""Shared endpoint dependencies: who is signed in."""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import User
from app.services.auth import user_for_token


def session_token(request: Request, settings: Settings = Depends(get_settings)) -> str | None:
    return request.cookies.get(settings.session_cookie_name)


def current_user(
    token: str | None = Depends(session_token), db: Session = Depends(get_db)
) -> User | None:
    return user_for_token(db, token)


def require_user(user: User | None = Depends(current_user)) -> User:
    """Guard for endpoints that need a signed-in user (401 otherwise)."""
    if user is None:
        raise ApiError(401, "not_signed_in", "Please sign in to continue.")
    return user
