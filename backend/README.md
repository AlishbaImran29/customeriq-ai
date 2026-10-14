# CustomerIQ AI — Backend

FastAPI + PostgreSQL API for the CustomerIQ AI dashboard.

**Status:** Phase 1 (skeleton). Implemented: settings, database connection,
tables + migration, consistent error responses, and `GET /api/v1/health`.
Not implemented yet: imports, analytics endpoints, ML predictions, AI assistant.

## Requirements

- Python 3.13
- PostgreSQL 18 running locally, with a `customeriq` database owned by the
  `customeriq_app` login (no superuser rights).

## First-time setup (Windows PowerShell, from `D:\CustomerIQ.AI\backend`)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env      # then open .env and fill in DB_PASSWORD
.\.venv\Scripts\alembic.exe upgrade head
```

`.env` holds secrets and is gitignored. Never commit it or share its contents.

## Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- Health check: http://127.0.0.1:8000/api/v1/health
- Interactive API docs: http://127.0.0.1:8000/docs

`/api/v1/health` returns `200 {"status": "ok", "database": "ok"}` when
PostgreSQL is reachable, otherwise `503` with `"database"` set to
`"not_configured"` or `"unavailable"` (details in the server log).

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Database tests are skipped automatically until `.env` is configured.

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Local PostgreSQL connection. Special characters in the password are handled. |
| `DATABASE_URL` | Optional full URL (`postgresql+psycopg://…`) for hosted databases; overrides the fields above. |
| `FRONTEND_ORIGINS` | Comma-separated browser origins allowed by CORS. |
| `OPENAI_API_KEY` | Phase 5 only. Server-side; never expose it to the frontend. |

## Error format

Every error response uses:

```json
{"error": {"code": "not_found", "message": "Not Found", "details": null}}
```

Validation errors list the field locations and reasons, never the submitted values.

## Database schema

| Table | Contents |
|---|---|
| `customers` | One row per `customer_id` from imports (email, optional name/country). |
| `orders` | One row per imported order: date, value, optional category/channel, optional `engagement_score` (0–100; NULL means not provided — never treated as 0). |
| `import_jobs` | Each uploaded file: status, row counts, row-level errors (no customer values). |

Create a new migration after changing models:

```powershell
.\.venv\Scripts\alembic.exe revision --autogenerate -m "describe change"
```
