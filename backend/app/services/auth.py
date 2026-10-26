"""Sign-in. Supabase Auth keeps the accounts and passwords; this file only checks a sign-in token and finds the person's row.

HOW A REQUEST IS CHECKED
1. The website signs the person in with Supabase (email + password, no email-confirmation step) and sends the token with every
   API call as `Authorization: Bearer <token>`.
2. The token is checked by asking Supabase who it belongs to (`/auth/v1/user`), so it works with any Supabase signing-key setup.
   A good answer is remembered for a minute so a page that makes ten calls asks Supabase once.
3. The person's row in our `users` table (same id as their Supabase account) holds their ROLE and whether they are approved.

WHO GETS IN. Because sign-up needs no email confirmation, anyone could create a Supabase account. So a new account is NOT allowed
to see customer data until the owner approves it (Team page). The very first account on a fresh site becomes the owner; if
OWNER_EMAIL is set, only that address can claim the owner role.
"""

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import User

logger = logging.getLogger(__name__)

TOKEN_CACHE_SECONDS = 60
TOKEN_CACHE_MAX = 500
LOGIN_TOUCH_MINUTES = 10                 # "last sign-in" is updated at most this often
OWNER_LOCK_ID = 727_001                  # serialises "who becomes the owner" across requests
TIMEOUT_SECONDS = 8

_cache: dict[str, tuple[float, "Identity"]] = {}


@dataclass(frozen=True)
class Identity:
    id: uuid.UUID
    email: str
    name: str


def reset_token_cache() -> None:
    _cache.clear()


def _name_of(payload: dict, email: str) -> str:
    meta = payload.get("user_metadata") or {}
    return (str(meta.get("name") or meta.get("full_name") or "").strip() or email.split("@")[0])[:100]


def identity_for_token(settings: Settings, token: str) -> Identity | None:
    """Who does this Supabase token belong to? None when it is not valid (expired, forged, signed out)."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise ApiError(503, "auth_not_configured", "Sign-in is not set up on the server. Add SUPABASE_URL and SUPABASE_ANON_KEY to the backend settings.")
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    request = urllib.request.Request(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/user", headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:               # noqa: S310 (the project's own Supabase address)
            payload = json.loads(response.read(100_000))
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 401, 403):
            return None
        raise ApiError(503, "auth_unreachable", "Sign-in could not be checked just now. Please try again in a moment.") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise ApiError(503, "auth_unreachable", "Sign-in could not be checked just now. Please try again in a moment.") from exc
    try:
        email = str(payload["email"]).strip().lower()
        identity = Identity(id=uuid.UUID(str(payload["id"])), email=email, name=_name_of(payload, email))
    except (KeyError, ValueError):
        return None
    if len(_cache) >= TOKEN_CACHE_MAX:
        _cache.clear()
    _cache[key] = (now + TOKEN_CACHE_SECONDS, identity)
    return identity


def user_for_identity(db: Session, settings: Settings, identity: Identity) -> User:
    """The person's row, created on their first visit. The first account becomes the owner; later ones wait for approval."""
    user = db.get(User, identity.id)
    if user is None:
        db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": OWNER_LOCK_ID})
        user = db.get(User, identity.id)                       # someone may have created it while we waited for the lock
    if user is None:
        owners = db.scalar(select(func.count()).select_from(User).where(User.role == "owner")) or 0
        wanted = (settings.owner_email or "").strip().lower()
        first_owner = owners == 0 and (not wanted or identity.email == wanted)
        user = User(id=identity.id, email=identity.email, name=identity.name, role="owner" if first_owner else "viewer", is_active=first_owner)
        try:
            with db.begin_nested():
                db.add(user)
                db.flush()
        except IntegrityError:
            user = db.get(User, identity.id)
            if user is None:
                raise
        else:
            logger.info("New account created (%s)", "owner" if first_owner else "waiting for approval")
    now = datetime.now(timezone.utc)
    if user.last_login_at is None or now - user.last_login_at > timedelta(minutes=LOGIN_TOUCH_MINUTES):
        user.last_login_at = now
    db.commit()
    return user
