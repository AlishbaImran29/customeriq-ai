import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    """A person who can sign in. Passwords are stored only as scrypt hashes."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)  # lower-cased
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set once the person has proved they own the address (a code sent by email).
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The pending verification code: only a hash is stored, and it expires quickly.
    verify_code_hash: Mapped[str | None] = mapped_column(String(64))
    verify_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verify_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    verify_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verify_send_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class UserSession(Base):
    """A signed-in browser. Only a SHA-256 hash of the cookie token is stored, so a
    database leak does not hand out working sessions."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
