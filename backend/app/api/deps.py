"""Shared endpoint dependencies: who is signed in."""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.core import permissions
from app.models import AuditLog, User
from app.services.auth import identity_for_token, user_for_identity


def bearer_token(request: Request) -> str | None:
    """The sign-in token the website sends with every call: `Authorization: Bearer <token>`."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


def current_user(
    token: str | None = Depends(bearer_token), db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> User | None:
    """The signed-in person (even if still waiting for approval), or None."""
    if not token:
        return None
    identity = identity_for_token(settings, token)
    return user_for_identity(db, settings, identity) if identity else None


def require_user(user: User | None = Depends(current_user)) -> User:
    """Guard for endpoints that need a signed-in, approved user (401 if signed out, 403 while waiting for the owner's approval)."""
    if user is None:
        raise ApiError(401, "not_signed_in", "Please sign in to continue.")
    if not user.is_active:
        raise ApiError(403, "account_pending", "Your account is waiting for the owner's approval.")
    return user


_ROLE_MESSAGES = {
    "owner": "Only the account owner can do this.",
    "staff": "Your account can only look at things. Ask the owner to make you staff.",
}


def enforce_role(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)) -> User:
    """The role check for every signed-in request, and the action log for every request that changes something.

    Reading is not logged (it would be noise); anything else is, with who, which route and whether it was allowed.
    The log holds the route and the ids in it, never what was typed."""
    method, path = request.method.upper(), request.url.path
    role = getattr(user, "role", None)                    # a missing role is allowed nothing: this fails closed
    ok = permissions.allowed(role, method, path)
    if method not in ("GET", "HEAD", "OPTIONS") or not ok:
        template = path                                   # "/api/v1/refunds/9/record" -> "/api/v1/refunds/{refund_id}/record"
        for name, value in request.path_params.items():
            template = template.replace(str(value), "{" + name + "}")
        db.add(AuditLog(
            actor_email=getattr(user, "email", "?")[:320], actor_role=(role or "none")[:10], method=method,
            route=template[:200], outcome="allowed" if ok else "denied",
            detail={"ids": {k: str(v)[:60] for k, v in request.path_params.items()}},
        ))
        db.commit()
    if not ok:
        needed = permissions.minimum_role(method, path)
        raise ApiError(403, "forbidden", _ROLE_MESSAGES.get(needed, "You are not allowed to do this."))
    return user
