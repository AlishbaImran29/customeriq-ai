"""Send win-back emails to at-risk (60+ days) and lost (180+ days) customers.

Same rules as the dashboard button: only customers who agreed to email, never anyone who unsubscribed, nobody twice
within 30 days, and never past the daily limit. Without BREVO_API_KEY nothing is really sent (test mode).

Usage (from backend/):
    .venv/Scripts/python.exe scripts/send_winback.py
    .venv/Scripts/python.exe scripts/send_winback.py --code WELCOME10 --value "10%"
    .venv/Scripts/python.exe scripts/send_winback.py --batch 50
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.services.email_auto import service  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--code", help="optional discount code to show in the email")
    parser.add_argument("--value", help='what the code gives, for example "10%%" or "Rs. 500"')
    parser.add_argument("--batch", type=int, default=service.BATCH, help="most emails in this run")
    args = parser.parse_args()
    settings = get_settings()
    with Session(get_engine()) as db:
        result = service.send_winback(db, settings, args.code, args.value, limit=args.batch)
        db.commit()
    mode = "TEST MODE (nothing really sent)" if not service.brevo_ready(settings) else "LIVE"
    print(f"{mode}: sent {result.sent}, failed {result.failed}, still waiting {result.remaining}, skipped {result.skipped or 'none'}")
    if result.message:
        print(result.message)


if __name__ == "__main__":
    main()
