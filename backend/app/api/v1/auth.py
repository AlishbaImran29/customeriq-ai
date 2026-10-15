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
from app.schemas.auth import AuthStatus, ChangePasswordRequest, LoginRequest, SetupRequest, UserOut
from app.services import auth as svc

router = APIRouter(prefix="/auth", tags=["auth"])

_SETUP_LOCK_ID = 727_001  # serialises "create the first account" across requests


def _user_out(user: User) -> UserOut:
    return UserOut(id=str(user.id), email=user.email, name=user.name, last_login_at=user.last_login_at)


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
    setup_required = svc.user_count(db) == 0
    return AuthStatus(
        setup_required=setup_required,
        setup_code_required=setup_required and settings.setup_code_required,
        authenticated=user is not None,
        user=_user_out(user) if user else None,
    )


@router.post("/setup", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def setup(
    body: SetupRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    """Create the first account. Only works while no account exists."""
    db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _SETUP_LOCK_ID})
    if svc.user_count(db) > 0:
        raise ApiError(409, "setup_done", "An account already exists. Please sign in instead.")
    svc.check_setup_code(settings, body.setup_code)
    user = svc.create_user(db, email=body.email, name=body.name, password=body.password)
    token, max_age = svc.create_session(db, user, settings, body.remember)
    db.commit()
    _set_cookie(response, settings, token, max_age)
    return _user_out(user)


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    user = svc.authenticate(db, body.email, body.password)
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
