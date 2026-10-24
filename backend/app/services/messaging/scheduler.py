"""Everything that is "due": one function the scheduler (or the "run due messages" button) calls.

Why one function: the hosting is serverless (Vercel), so nothing can run in the background by itself. Something outside
has to knock on a protected address now and then (see api/v1/internal.py), and each knock does ALL the due work in one
bounded pass: messages waiting for the end of quiet hours or a retry, customer files waiting to be stored, review
requests, campaign batches and journey steps. Every step has a limit, so one pass is always short, and doing the same
pass twice never sends anything twice (every message has an idempotency key).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.messaging import followups, media, service

logger = logging.getLogger(__name__)


def run_due(db: Session, settings: Settings, now: datetime | None = None) -> dict[str, dict]:
    """Run every kind of due work. Each part is isolated: one failing part is reported and the others still run.
    Commits after each part."""
    now = now or datetime.now(timezone.utc)
    parts = {
        "queue": lambda: service.process_queue(db, settings, now),
        "media": lambda: media.process_pending_media(db, settings, now, limit=3),
        "reviews": lambda: followups.run_review_requests(db, settings, now),
    }
    from app.services.messaging import campaigns, journeys            # imported here: they use the sending code above

    from app.services.messaging import cod_confirm

    from app.services.workflows import engine as workflow_engine

    parts["cod"] = lambda: cod_confirm.mark_overdue(db, now)
    parts["workflows"] = lambda: {**workflow_engine.tick(db, settings, now), **workflow_engine.run_due_jobs(db, settings, now)}
    parts["campaigns"] = lambda: campaigns.send_due_batches(db, settings, now)
    parts["journeys"] = lambda: journeys.run_journeys(db, settings, now)
    results: dict[str, dict] = {}
    for name, work in parts.items():
        try:
            results[name] = work()
            db.commit()
        except Exception:  # noqa: BLE001 (report it, keep going)
            logger.exception("Scheduler part %s failed", name)
            db.rollback()
            results[name] = {"error": 1}
    return results
