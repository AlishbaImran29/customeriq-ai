"""Send one test email of every template (COD confirmation, COD reminder, win-back, new product) to SENDER_EMAIL.

Uses sample data only, so no customers or database are needed. Needs BREVO_API_KEY and SENDER_EMAIL in backend/.env
(SENDER_EMAIL must be a sender you verified in Brevo). Without a key the emails are only rendered (test mode).

Usage (from backend/):
    .venv/Scripts/python.exe scripts/send_test_emails.py
    .venv/Scripts/python.exe scripts/send_test_emails.py --save-html previews     # also write the HTML files to open in a browser
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.errors import ApiError  # noqa: E402
from app.services.email_auto import render, service  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--save-html", metavar="FOLDER", help="also save every email as an .html file in this folder")
    args = parser.parse_args()
    settings = get_settings()
    if args.save_html:
        folder = Path(args.save_html)
        folder.mkdir(parents=True, exist_ok=True)
        for key in render.TEMPLATES:
            (folder / f"{key}.html").write_text(render.render(key, render.sample_data(key))[1], encoding="utf-8")
        print(f"Saved the HTML files in {folder.resolve()}")
    try:
        mails = service.send_test_emails(settings)
    except ApiError as exc:
        sys.exit(exc.message)
    live = service.brevo_ready(settings)
    for mail in mails:
        print(f"{mail.result.upper():7} {mail.subject}" + (f"  ({mail.error})" if mail.error else ""))
    print(f"Sent to {settings.sender_email}." if live else "TEST MODE: BREVO_API_KEY is not set, so nothing was really sent.")


if __name__ == "__main__":
    main()
