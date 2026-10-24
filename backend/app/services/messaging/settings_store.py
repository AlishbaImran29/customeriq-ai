"""The seller's messaging settings (one row) and the dry-run rule."""

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import MessagingSettings


def get_row(db: Session) -> MessagingSettings:
    """The settings row, created with safe defaults (dry run ON) if it is somehow missing."""
    row = db.get(MessagingSettings, 1)
    if row is None:
        row = MessagingSettings(id=1)
        db.add(row)
        db.flush()
    return row


def dry_run_forced(settings: Settings) -> bool:
    """True when the SERVER says dry run (MESSAGING_DRY_RUN=true): the settings page cannot turn it off."""
    return settings.messaging_dry_run is True


def effective_dry_run(settings: Settings, row: MessagingSettings) -> bool:
    """Is nothing really sent? Yes when the server forces it, or when the seller's toggle is on (the default)."""
    return dry_run_forced(settings) or bool(row.dry_run)
