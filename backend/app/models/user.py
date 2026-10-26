import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    """A person who can sign in. Their account and password live in Supabase Auth; this row holds what the app adds:
    the role (owner > staff > viewer, see core/permissions.py) and whether the owner has approved them."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('owner', 'staff', 'viewer')", name="user_role_known"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)  # the same id as their Supabase Auth account
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)  # lower-cased
    name: Mapped[str] = mapped_column(String(100))
    # False = waiting for the owner's approval (no access to any data yet). The first account on a new site is approved at once.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    role: Mapped[str] = mapped_column(String(10), default="viewer", server_default="viewer")
