"""Accounts and sessions: create users, check passwords, manage sign-in sessions."""

import hashlib
import hmac
import secrets
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
from app.services import mailer

CODE_MINUTES = 15
RESEND_COOLDOWN_SECONDS = 60
MAX_CODES_PER_HOUR = 5
MAX_CODE_ATTEMPTS = 5

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


def verified_user_count(db: Session) -> int:
    """Accounts that count as real owners: those whose email is confirmed."""
    return db.scalar(select(func.count()).select_from(User).where(User.email_verified_at.is_not(None))) or 0


def _checked_details(email: str, name: str, password: str) -> tuple[str, str]:
    email = normalise_email(email)
    name = name.strip() or email.split("@")[0]
    if not is_valid_email(email):
        raise ApiError(422, "invalid_email", "Please enter a valid email address.", {"field": "email"})
    if len(name) > 100:
        raise ApiError(422, "invalid_name", "That name is too long (100 characters at most).", {"field": "name"})
    problem = password_problem(password, email)
    if problem:
        raise ApiError(422, "weak_password", problem, {"field": "password"})
    return email, name


def create_user(db: Session, *, email: str, name: str, password: str, verified: bool = True, role: str = "viewer") -> User:
    """Validate and create an account. Raises ApiError(422/409) with friendly messages.

    `verified=False` leaves the email unconfirmed until the person enters the code we send.
    """
    email, name = _checked_details(email, name, password)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise ApiError(409, "email_taken", "An account with this email already exists.", {"field": "email"})
    user = User(
        email=email, name=name, password_hash=hash_password(password), role=role,
        email_verified_at=datetime.now(UTC) if verified else None,
    )
    db.add(user)
    db.flush()
    return user


def refresh_unverified(db: Session, user: User, *, name: str, password: str) -> None:
    """Someone signs up again with an address that never confirmed: keep the latest name and password."""
    _, checked_name = _checked_details(user.email, name, password)
    user.name = checked_name
    user.password_hash = hash_password(password)
    db.flush()


def delete_unverified(db: Session) -> None:
    """Drop accounts that never confirmed their email (used when the owner restarts setup)."""
    db.execute(delete(User).where(User.email_verified_at.is_(None)))
    db.flush()


# --- email verification --------------------------------------------------------------------

def _code_hash(user: User, code: str) -> str:
    return hashlib.sha256(f"{user.id}:{code.strip()}".encode()).hexdigest()


def issue_code(db: Session, user: User, settings: Settings) -> None:
    """Create a fresh 6-digit code and email it. Limits how often one address can be mailed."""
    now = datetime.now(UTC)
    sent_at = user.verify_sent_at
    if sent_at is not None and (now - sent_at).total_seconds() < RESEND_COOLDOWN_SECONDS:
        wait = RESEND_COOLDOWN_SECONDS - int((now - sent_at).total_seconds())
        raise ApiError(429, "code_cooldown", f"Please wait {wait} seconds before asking for another code.",
                       {"retryAfterSeconds": wait})
    count = user.verify_send_count if sent_at is not None and (now - sent_at) < timedelta(hours=1) else 0
    if count >= MAX_CODES_PER_HOUR:
        raise ApiError(429, "too_many_codes", "Too many codes were requested. Please try again in an hour.")
    code = f"{secrets.randbelow(10**6):06d}"
    user.verify_code_hash = _code_hash(user, code)
    user.verify_expires_at = now + timedelta(minutes=CODE_MINUTES)
    user.verify_attempts = 0
    user.verify_sent_at = now
    user.verify_send_count = count + 1
    db.flush()
    mailer.send_verification_code(settings, user.email, user.name, code, CODE_MINUTES)


def check_code(db: Session, user: User, code: str) -> None:
    """Mark the email as verified if the code is right. Wrong guesses are counted in the database."""
    now = datetime.now(UTC)
    if not user.verify_code_hash or user.verify_expires_at is None or user.verify_expires_at <= now:
        raise ApiError(400, "code_expired", "That code has expired. Please ask for a new one.",
                       {"field": "code"})
    if user.verify_attempts >= MAX_CODE_ATTEMPTS:
        raise ApiError(429, "too_many_attempts", "Too many wrong codes. Please ask for a new code.",
                       {"field": "code"})
    if not hmac.compare_digest(_code_hash(user, code), user.verify_code_hash):
        user.verify_attempts += 1
        db.commit()  # keep the count even though we raise
        raise ApiError(400, "invalid_code", "That code is not correct.", {"field": "code"})
    user.email_verified_at = now
    user.verify_code_hash = None
    user.verify_expires_at = None
    user.verify_attempts = 0
    db.flush()


def user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalise_email(email)))


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
