"""Import an orders file straight into a HOSTED PostgreSQL (e.g. Supabase) from this computer.

Use it when a file is too big for the website's upload (Vercel allows request bodies of at most
4.5 MB). It runs the SAME checks and the SAME import as the website: valid rows are saved,
invalid rows are rejected and listed, and an order_id that already exists is updated with the
file's values (blank optional columns keep what is saved).

It asks for the connection details; the password is typed at a hidden prompt and is used only
for this run (it is never saved to a file).

Usage (from backend/):
    .venv/Scripts/python.exe scripts/import_remote.py FILE.csv             # asks for host, user, password...
    .venv/Scripts/python.exe scripts/import_remote.py FILE.csv --dry-run   # only checks the file; touches no database
    .venv/Scripts/python.exe scripts/import_remote.py FILE.csv --current   # use backend/.env instead (local test)
"""

import argparse
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def check_file(path: Path) -> bytes:
    """Read the file and run the website's own file-level and row-level checks (no database)."""
    from app.services.import_files import file_type_of, parse_file
    from app.services.import_formats import convert
    from app.services.import_validation import validate_rows

    content = path.read_bytes()
    parsed = parse_file(content, file_type_of(path.name))
    converted = convert(parsed)
    result = validate_rows(converted.parsed)
    problems = converted.skipped + result.errors
    print(f"File: {path.name} ({len(content) / 1024 / 1024:.1f} MB), format: {converted.file_format}")
    print(f"Rows in file: {len(parsed.rows):,}  valid: {len(result.rows):,}  rejected: {result.rejected_rows + len(converted.skipped):,}")
    for error in sorted(problems, key=lambda e: e.row or 0)[:10]:
        print(f"  row {error.row}, {error.column}: {error.message}")
    if len(problems) > 10:
        print(f"  ... and {len(problems) - 10:,} more problems")
    return content


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="check the file only; do not connect to a database")
    parser.add_argument("--current", action="store_true", help="use backend/.env instead of asking (local test)")
    args = parser.parse_args()
    if not args.file.is_file():
        print(f"File not found: {args.file}")
        return 1

    if args.dry_run:
        check_file(args.file)
        print("\nDry run: nothing was saved.")
        return 0

    if not args.current:
        import migrate_remote

        migrate_remote.ask_connection_details(action=f"IMPORT '{args.file.name}' into")
    # Environment variables are ready now, so the right database is used from here on.
    from sqlalchemy.orm import Session

    from app.db.session import check_database, get_engine
    from app.services.import_service import run_import

    content = check_file(args.file)
    status = check_database()
    if status != "ok":
        print(f"\nCould not connect to the database ({status}). Check the host, user, and password.")
        return 1
    print("\nConnected. Importing (this can take a minute)...")
    with Session(get_engine()) as db:
        job = run_import(db, args.file.name, args.file.suffix.lstrip(".").lower(), content)
    print(
        f"\nDone. New orders: {job.rows_imported:,}, updated orders: {job.rows_updated:,}, "
        f"rejected rows: {job.rows_rejected:,}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
