"""The address a SCHEDULER calls to run everything that is due (Auto Messenger part 5).

WHY THIS DESIGN. The site runs on Vercel, which has no background workers: nothing can run "every hour" by itself. So
something outside knocks on this address on a timetable. We use a GitHub Actions schedule (see
.github/workflows/scheduler.yml): it is free for a private repository's small jobs, needs no extra account, and the
timetable is a text file in the repository that can be read and changed. (Supabase's pg_cron plus pg_net could do the same
from inside the database, but it needs two extensions and SQL set up by hand, and its secret would live in the database.)

SECURITY. The address is public, so it is protected with a shared secret: the caller must send the header
X-Scheduler-Secret with the value of SCHEDULER_SECRET, compared in constant time. Without a configured secret the address
refuses everyone. Every pass is bounded and safe to repeat: running it twice never sends a message twice.
"""

import hmac
import logging

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import error_body
from app.db.session import get_db
from app.services.messaging import scheduler

logger = logging.getLogger(__name__)
router = APIRouter(tags=["internal"])


@router.post("/internal/run-scheduler", summary="Run everything that is due (called by the scheduler, needs the secret)")
def run_scheduler(
    x_scheduler_secret: str | None = Header(default=None), db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
):
    expected = settings.scheduler_secret.get_secret_value() if settings.scheduler_secret else ""
    if not expected.strip():
        return JSONResponse(status_code=503, content=error_body("scheduler_not_configured", "SCHEDULER_SECRET is not set on the server."))
    if not x_scheduler_secret or not hmac.compare_digest(expected, x_scheduler_secret):
        logger.warning("Scheduler call refused: wrong or missing secret")
        return JSONResponse(status_code=403, content=error_body("forbidden", "The scheduler secret is not correct."))
    return {"ok": True, "results": scheduler.run_due(db, settings)}
