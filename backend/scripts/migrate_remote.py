"""Create or update the database tables on a HOSTED PostgreSQL (e.g. Supabase) from this computer.

Run it once before the first deployment, and again after any update that adds database
changes. It asks for the connection details; the password is typed at a hidden prompt and
is used only for this run (it is never saved to a file).

Usage (from backend/):
    .venv/Scripts/python.exe scripts/migrate_remote.py            # asks for host, user, password...
    .venv/Scripts/python.exe scripts/migrate_remote.py --current  # use backend/.env instead (local test)
"""

import getpass
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
MAX_ATTEMPTS = 3
RETRY_SECONDS = 6
sys.path.insert(0, str(BACKEND))


def ask_connection_details(action: str = "update the tables on") -> None:
    print("Enter the connection details from Supabase (Connect -> Session pooler).\n")
    host = input("Host (contains 'pooler.supabase.com'): ").strip()
    port = input("Port [5432]: ").strip() or "5432"
    database = input("Database [postgres]: ").strip() or "postgres"
    user = input("User (like postgres.abcdefghij): ").strip()
    password = getpass.getpass("Password (typing is hidden): ")
    if not host or not user or not password:
        raise SystemExit("Host, user and password are all needed. Nothing was changed.")
    if "pooler.supabase.com" not in host and "supabase" in host:
        print("\n  Note: this does not look like the 'Session pooler' host. It may not work on every network.")
    # Environment variables override backend/.env, and only for this run.
    os.environ.update(
        DB_HOST=host, DB_PORT=port, DB_NAME=database, DB_USER=user, DB_PASSWORD=password,
        DB_SSLMODE="require", DATABASE_URL="",
    )
    print(f"\nAbout to {action} {host} (database '{database}', user '{user}').")
    if input("Type yes to continue (anything else cancels): ").strip().lower() not in ("yes", "y"):
        raise SystemExit("Cancelled. Nothing was changed. Run the command again and type: yes")


def main() -> int:
    if "--current" not in sys.argv:
        ask_connection_details()

    # Imported only after the environment is ready, so the right database is used.
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect
    from sqlalchemy.exc import OperationalError

    from app.db.session import check_database, get_engine

    status = check_database()
    if status != "ok":
        print(f"\nCould not connect to the database ({status}). Check the host, user, and password.")
        return 1
    print("\nConnected. Updating the tables...")
    # Close the connection used for the check above: a free hosted database allows only a few
    # connections, and the migration opens its own.
    get_engine().dispose()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
            break
        except OperationalError as exc:
            if attempt == MAX_ATTEMPTS:
                print(f"\nThe database kept dropping the connection ({type(exc.orig).__name__}). Nothing was changed.")
                print("Wait a few minutes (or open the Supabase dashboard so the project wakes up) and run this again.")
                return 1
            print(f"\nThe connection was dropped (attempt {attempt} of {MAX_ATTEMPTS}). Trying again in {RETRY_SECONDS} seconds...")
            time.sleep(RETRY_SECONDS)
    tables = sorted(inspect(get_engine()).get_table_names())
    print("\nDone. Tables in the database:", ", ".join(tables))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
