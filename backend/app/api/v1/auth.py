"""Who am I. Sign-up, sign-in and passwords are handled by Supabase Auth in the browser; the backend only checks the token."""

from fastapi import APIRouter, Depends

from app.api.deps import current_user
from app.core.errors import ApiError
from app.models import User
from app.schemas.auth import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserOut, summary="The signed-in person, their role, and whether the owner has approved them")
def me(user: User | None = Depends(current_user)) -> UserOut:
    if user is None:
        raise ApiError(401, "not_signed_in", "Please sign in to continue.")
    return UserOut(id=str(user.id), email=user.email, name=user.name, last_login_at=user.last_login_at, role=user.role, is_active=user.is_active)  # type: ignore[arg-type]
