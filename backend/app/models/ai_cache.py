from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AiCache(TimestampMixin, Base):
    """An AI answer kept under a fingerprint of the question, so asking again is free (Auto Messenger campaign drafts)."""

    __tablename__ = "ai_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)       # sha256 of kind + inputs
    kind: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSONB)
