from datetime import datetime

from pydantic import Field

from app.schemas.imports import CamelModel


class UserOut(CamelModel):
    id: str
    email: str
    name: str
    last_login_at: datetime | None


class AuthStatus(CamelModel):
    """What the sign-in page needs to know. Safe to show before signing in."""

    setup_required: bool          # no account exists yet: show "create your account"
    setup_code_required: bool     # creating the first account needs the owner's setup code
    authenticated: bool
    user: UserOut | None


class LoginRequest(CamelModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)
    remember: bool = False


class SetupRequest(CamelModel):
    name: str = Field(default="", max_length=100)
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)
    setup_code: str | None = Field(default=None, max_length=200)
    remember: bool = True


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)
