"""Sign-in endpoints. The session lives in an HttpOnly cookie (never readable by page scripts)."""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_user, session_token
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.security import verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    AuthStatus,
    ChangePasswordRequest,
    LoginRequest,
    ResendRequest,
    SetupRequest,
    SignupRequest,
    UserOut,
    VerificationPending,
    VerifyRequest,
)
from app.services import auth as svc

router = APIRouter(prefix="/auth", tags=["auth"])

_SETUP_LOCK_ID = 727_001  # serialises "create the first account" across requests


def _user_out(user: User) -> UserOut:
    return UserOut(id=str(user.id), email=user.email, name=user.name, last_login_at=user.last_login_at, role=user.role)  # type: ignore[arg-type]


def _set_cookie(response: Response, settings: Settings, token: str, max_age: int | None) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age,  # None = until the browser is closed
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name, path="/", httponly=True,
        secure=settings.cookie_secure, samesite="lax",
    )


@router.get("/status", response_model=AuthStatus)
def auth_status(
    user: User | None = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthStatus:
    """Public: tells the sign-in page whether to show "sign in" or "create your account"."""
    # Only confirmed accounts count: an owner who mistyped their email can start setup again.
    setup_required = svc.verified_user_count(db) == 0
    return AuthStatus(
        setup_required=setup_required,
        setup_code_required=setup_required and settings.setup_code_required,
        authenticated=user is not None,
        user=_user_out(user) if user else None,
        signup_open=settings.signup_open and not setup_required,
        verification_enabled=settings.email_verification_required,
    )


@router.post("/setup", status_code=status.HTTP_201_CREATED, response_model=UserOut | VerificationPending)
def setup(
    body: SetupRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserOut | VerificationPending:
    """Create the first account. Only works while no confirmed account exists.

    With email set up, the owner must confirm their address with a code before signing in.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _SETUP_LOCK_ID})
    if svc.verified_user_count(db) > 0:
        raise ApiError(409, "setup_done", "An account already exists. Please sign in instead.")
    svc.check_setup_code(settings, body.setup_code)
    svc.delete_unverified(db)  # a previous attempt that never confirmed (for example a typo in the email)
    verify = settings.email_verification_required
    user = svc.create_user(db, email=body.email, name=body.name, password=body.password, verified=not verify, role="owner")   # the first account is the owner
    if verify:
        svc.issue_code(db, user, settings)
        db.commit()
        response.status_code = status.HTTP_202_ACCEPTED
        return VerificationPending(email=user.email)
    token, max_age = svc.create_session(db, user, settings, body.remember)
    db.commit()
    _set_cookie(response, settings, token, max_age)
    return _user_out(user)


@router.post("/signup", status_code=status.HTTP_202_ACCEPTED, response_model=VerificationPending)
def signup(
    body: SignupRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> VerificationPending:
    """Public sign-up: create an unconfirmed account and email a 6-digit code."""
    if not settings.signup_open:
        raise ApiError(403, "signup_closed", "Creating accounts is turned off on this site.")
    if svc.verified_user_count(db) == 0:
        raise ApiError(403, "setup_required", "The owner account has to be created first.")
    existing = svc.user_by_email(db, body.email)
    if existing is not None and existing.email_verified_at is not None:
        raise ApiError(409, "email_taken", "An account with this email already exists. Please sign in instead.",
                       {"field": "email"})
    if existing is not None:
        svc.refresh_unverified(db, existing, name=body.name, password=body.password)
        user = existing
    else:
        user = svc.create_user(db, email=body.email, name=body.name, password=body.password, verified=False)
    svc.issue_code(db, user, settings)
    db.commit()
    return VerificationPending(email=user.email)


@router.post("/verify", response_model=UserOut)
def verify_email(
    body: VerifyRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    """Confirm the email with the emailed code, then sign in."""
    user = svc.user_by_email(db, body.email)
    if user is None or user.email_verified_at is not None or not user.is_active:
        raise ApiError(400, "invalid_code", "That code is not correct.", {"field": "code"})
    svc.check_code(db, user, body.code)
    token, max_age = svc.create_session(db, user, settings, body.remember)
    db.commit()
    _set_cookie(response, settings, token, max_age)
    return _user_out(user)


@router.post("/resend", status_code=status.HTTP_202_ACCEPTED, response_model=VerificationPending)
def resend_code(
    body: ResendRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> VerificationPending:
    """Send a new code. Always answers the same way, so it cannot be used to find out who has an account."""
    user = svc.user_by_email(db, body.email)
    if settings.email_verification_required and user is not None and user.email_verified_at is None:
        try:
            svc.issue_code(db, user, settings)
            db.commit()
        except ApiError as exc:
            if exc.code not in ("code_cooldown", "too_many_codes"):
                raise
    return VerificationPending(email=body.email.strip().lower())


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    user = svc.authenticate(db, body.email, body.password)
    if settings.email_verification_required and user.email_verified_at is None:
        # Right password, but the email was never confirmed: send a fresh code and show the code screen.
        try:
            svc.issue_code(db, user, settings)
        except ApiError as exc:
            if exc.code not in ("code_cooldown", "too_many_codes"):
                raise
        db.commit()
        raise ApiError(403, "email_not_verified", f"Please confirm your email first. We sent a code to {user.email}.",
                       {"email": user.email})
    token, max_age = svc.create_session(db, user, settings, body.remember)
    db.commit()
    _set_cookie(response, settings, token, max_age)
    return _user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    token: str | None = Depends(session_token),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    svc.end_session(db, token)
    db.commit()
    _clear_cookie(response, settings)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_user)) -> UserOut:
    return _user_out(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    """Change your own password and sign out every other browser."""
    svc.verify_current_password(user, body.current_password)
    if verify_password(body.new_password, user.password_hash):
        raise ApiError(
            422, "same_password", "Choose a password you haven't used here before.",
            {"field": "newPassword"},
        )
    svc.set_password(db, user, body.new_password)
    svc.end_other_sessions(db, user, request.cookies.get(settings.session_cookie_name))
    db.commit()
