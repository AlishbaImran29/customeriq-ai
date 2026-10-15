"""Manage sign-in accounts from the command line.

Use this to create the first account without the website's setup form, add a
teammate, reset a forgotten password, or switch an account off. Passwords are
typed at a hidden prompt, so they never appear in your command history.

Usage (from backend/):
    .venv/Scripts/python.exe scripts/manage_users.py list
    .venv/Scripts/python.exe scripts/manage_users.py create you@company.com --name "Your Name"
    .venv/Scripts/python.exe scripts/manage_users.py reset-password you@company.com
    .venv/Scripts/python.exe scripts/manage_users.py deactivate you@company.com
    .venv/Scripts/python.exe scripts/manage_users.py activate you@company.com
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.errors import ApiError  # noqa: E402
from app.core.security import normalise_email  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.models import User, UserSession  # noqa: E402
from app.services import auth  # noqa: E402


def ask_new_password() -> str:
    first = getpass.getpass("New password (typing is hidden): ")
    if first != getpass.getpass("Type it again: "):
        raise SystemExit("The two passwords did not match. Nothing was changed.")
    return first


def find(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(User.email == normalise_email(email)))
    if user is None:
        raise SystemExit(f"No account found for {email}. Run the 'list' command to see accounts.")
    return user


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show all accounts")
    create = sub.add_parser("create", help="create an account")
    create.add_argument("email")
    create.add_argument("--name", default="")
    for name in ("reset-password", "deactivate", "activate"):
        sub.add_parser(name).add_argument("email")
    args = parser.parse_args()

    with Session(get_engine()) as db:
        try:
            if args.command == "list":
                users = db.scalars(select(User).order_by(User.created_at)).all()
                if not users:
                    print("No accounts yet. Create one with: manage_users.py create you@company.com")
                for u in users:
                    last = u.last_login_at.strftime("%Y-%m-%d %H:%M") if u.last_login_at else "never"
                    print(f"{u.email:<36} {u.name:<20} {'active' if u.is_active else 'DEACTIVATED':<12} last sign-in: {last}")
            elif args.command == "create":
                user = auth.create_user(db, email=args.email, name=args.name, password=ask_new_password())
                db.commit()
                print(f"Created account for {user.email}. They can sign in on the website now.")
            elif args.command == "reset-password":
                user = find(db, args.email)
                auth.set_password(db, user, ask_new_password())
                # Anyone signed in with the old password is signed out.
                db.execute(delete(UserSession).where(UserSession.user_id == user.id))
                db.commit()
                print(f"Password changed for {user.email}. They were signed out on all devices.")
            else:
                user = find(db, args.email)
                user.is_active = args.command == "activate"
                if not user.is_active:
                    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
                db.commit()
                print(f"{user.email} is now {'active' if user.is_active else 'deactivated (signed out everywhere)'}.")
        except ApiError as error:  # friendly messages from the same rules the website uses
            raise SystemExit(f"Could not do that: {error.message}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
