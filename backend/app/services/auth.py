"""Accounts and sessions: create users, check passwords, manage sign-in sessions."""

import hmac
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import (
    hash_password,
    hash_token,
    is_valid_email,
    new_session_token,
    normalise_email,
    password_problem,
    verify_password,
)
from app.models import User, UserSession

MAX_FAILED_LOGINS = 8
LOCK_SECONDS = 15 * 60
FAILURE_WINDOW_SECONDS = 15 * 60

# Compared against when the email is unknown, so the response time does not reveal
# whether an account exists.
_DUMMY_HASH = hash_password("not-a-real-password")


# --- brute-force protection (in memory: fine for one server, resets on restart) -------

@dataclass
class _Attempts:
    failures: int = 0
    first_failure: float = 0.0
    locked_until: float = 0.0


_attempts: dict[str, _Attempts] = {}
_attempts_lock = threading.Lock()


def reset_login_limits() -> None:
    with _attempts_lock:
        _attempts.clear()


def _check_not_locked(email: str) -> None:
    with _attempts_lock:
        state = _attempts.get(email)
        remaining = int(state.locked_until - time.monotonic()) if state else 0
    if remaining > 0:
        minutes = max(1, (remaining + 59) // 60)
        raise ApiError(
            429,
            "too_many_attempts",
            f"Too many sign-in attempts. Please wait about {minutes} minute"
            f"{'s' if minutes != 1 else ''} and try again.",
            {"retryAfterSeconds": remaining},
        )


def _record_failure(email: str) -> None:
    now = time.monotonic()
    with _attempts_lock:
        state = _attempts.setdefault(email, _Attempts(first_failure=now))
        if now - state.first_failure > FAILURE_WINDOW_SECONDS:
            state.failures, state.first_failure = 0, now
        state.failures += 1
        if state.failures >= MAX_FAILED_LOGINS:
            state.locked_until = now + LOCK_SECONDS
            state.failures = 0


def _clear_failures(email: str) -> None:
    with _attempts_lock:
        _attempts.pop(email, None)


# --- users -----------------------------------------------------------------------------

def user_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0


def create_user(db: Session, *, email: str, name: str, password: str) -> User:
    """Validate and create an account. Raises ApiError(422/409) with friendly messages."""
    email = normalise_email(email)
    name = name.strip() or email.split("@")[0]
    if not is_valid_email(email):
        raise ApiError(422, "invalid_email", "Please enter a valid email address.", {"field": "email"})
    if len(name) > 100:
        raise ApiError(422, "invalid_name", "That name is too long (100 characters at most).", {"field": "name"})
    problem = password_problem(password, email)
    if problem:
        raise ApiError(422, "weak_password", problem, {"field": "password"})
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise ApiError(409, "email_taken", "An account with this email already exists.", {"field": "email"})
    user = User(email=email, name=name, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    """Return the user for a correct email + password, else a generic 401."""
    email = normalise_email(email)
    _check_not_locked(email)
    user = db.scalar(select(User).where(User.email == email))
    password_ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok or not user.is_active:
        _record_failure(email)
        raise ApiError(401, "invalid_credentials", "That email or password is not correct.")
    _clear_failures(email)
    return user


def verify_current_password(user: User, password: str) -> None:
    """For "change password": the current password must be right (rate-limited like sign-in)."""
    key = f"password-change:{user.email}"
    _check_not_locked(key)
    if not verify_password(password, user.password_hash):
        _record_failure(key)
        raise ApiError(400, "wrong_password", "Your current password is not correct.",
                       {"field": "currentPassword"})
    _clear_failures(key)


def check_setup_code(settings: Settings, supplied: str | None) -> None:
    """Raise unless the setup code is right (guesses are rate-limited)."""
    if settings.setup_code_required:
        _check_not_locked("setup-code")
        if not setup_code_matches(settings, supplied):
            _record_failure("setup-code")
            raise ApiError(403, "invalid_setup_code", "That setup code is not correct.",
                           {"field": "setupCode"})
        _clear_failures("setup-code")


def set_password(db: Session, user: User, new_password: str) -> None:
    problem = password_problem(new_password, user.email)
    if problem:
        raise ApiError(422, "weak_password", problem, {"field": "newPassword"})
    user.password_hash = hash_password(new_password)


def setup_code_matches(settings: Settings, supplied: str | None) -> bool:
    if not settings.setup_code_required:
        return True
    assert settings.setup_code is not None
    return hmac.compare_digest(
        (supplied or "").strip().encode(), settings.setup_code.get_secret_value().strip().encode()
    )


# --- sessions ----------------------------------------------------------------------------

def create_session(db: Session, user: User, settings: Settings, remember: bool) -> tuple[str, int | None]:
    """Create a session. Returns (cookie token, cookie max-age seconds or None for a
    browser-session cookie)."""
    now = datetime.now(UTC)
    lifetime = (
        timedelta(days=settings.remember_session_days) if remember else timedelta(hours=settings.session_hours)
    )
    db.execute(delete(UserSession).where(UserSession.expires_at < now))  # tidy up old ones
    token = new_session_token()
    db.add(UserSession(token_hash=hash_token(token), user_id=user.id, created_at=now, expires_at=now + lifetime))
    user.last_login_at = now
    db.flush()
    return token, int(lifetime.total_seconds()) if remember else None


def user_for_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    row = db.execute(
        select(User, UserSession)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.token_hash == hash_token(token))
    ).first()
    if row is None:
        return None
    user, session = row
    if session.expires_at <= datetime.now(UTC) or not user.is_active:
        return None
    return user


def end_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))


def end_other_sessions(db: Session, user: User, keep_token: str | None) -> None:
    """Sign the user out everywhere except the current browser (e.g. after a password change)."""
    stmt = delete(UserSession).where(UserSession.user_id == user.id)
    if keep_token:
        stmt = stmt.where(UserSession.token_hash != hash_token(keep_token))
    db.execute(stmt)
