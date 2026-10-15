# CustomerIQ AI — Backend

FastAPI + PostgreSQL API for the CustomerIQ AI dashboard.

**Status:** Phase 5. Implemented: database + migrations, CSV/XLSX imports,
descriptive analytics endpoints (Phase 3), and the AI Business Assistant.
Not implemented yet: trained ML predictions (churn probability, predicted CLV,
revenue forecast) — these are always returned as `null` with a reason.

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
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Local PostgreSQL connection. Special characters in the password are handled. |
| `DATABASE_URL` | Optional full URL (`postgresql+psycopg://…`) for hosted databases; overrides the fields above. |
| `FRONTEND_ORIGINS` | Comma-separated browser origins allowed by CORS. |
| `AI_PROVIDER` | `anthropic` (default, Claude) or `openai`. |
| `ANTHROPIC_API_KEY` | Enables the assistant with Claude. Server-side only. Needs API credits in the Claude Console (separate from Claude Pro/Max). |
| `ANTHROPIC_MODEL` | Claude model ID (default `claude-opus-5-5`). |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | Used only when `AI_PROVIDER=openai` (default model `gpt-6-luna`). |

## Imports

| Endpoint | Purpose |
| --- | --- |
| `POST /api/v1/imports` | Upload one file (multipart field `file`). Returns `201` with the import result. |
| `GET /api/v1/imports?limit=20` | Recent imports, newest first (no row errors). |
| `GET /api/v1/imports/{id}` | One import, including its row errors. |

Rules:

- **Files:** `.csv` (UTF-8 or Windows-1252) or `.xlsx` (first sheet), up to 10 MB
  and 50,000 data rows. `.xls` is rejected with a "save as .xlsx" message.
- **Required columns:** `customer_id, email, order_id, order_date, order_value`.
  Optional: `first_name, last_name, country, product_category, channel, engagement`.
  Header names ignore case, spaces, and dashes.
- **File-level problems** (wrong type, too large, empty, missing/duplicate
  columns) return an error and save nothing.
- **Row-level problems** reject only that row. Valid rows are saved; the
  response lists up to 200 problems as `{row, column, message}`. Row numbers
  match Excel (header = row 1). Messages never repeat the cell values.
- **Existing `order_id`** → the order is updated with the new values
  (`rowsUpdated`). Blank optional cells keep the previous value.
- **`engagement`** must be 0–100. Blank means "not provided" (stored as NULL),
  never 0.
- Logs record counts only, never file contents or customer details.

A made-up sample file for trying the import: `tests/fixtures/sample_orders.csv`
(its last row is intentionally invalid). Delete those `DEMO-` rows afterwards if
you upload it to a real database.

## AI Business Assistant

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/assistant/status` | `{provider, configured, model, dataAsOf, customerCount}`. Never calls the AI provider. |
| `POST /api/v1/assistant/chat` | Body `{"messages": [{"role": "user", "content": "…"}]}` (max 20 messages, 2,000 characters each; last must be from the user). |

- Without the provider's API key the chat returns `503 assistant_not_configured`.
- With no imported data it returns a fixed message (`answeredBy: "system"`) and
  does not call the AI provider.
- The model receives only the Phase 3 summary (KPIs, segments, monthly revenue,
  drivers, recommendations, and up to 10 customers by **customer_id only**).
  **Customer names and emails are never sent.**
- **Claude:** the system prompt (rules + data summary) is marked for prompt
  caching, so follow-up questions on unchanged data reuse it at a lower price;
  server-side fallbacks (`fallbacks: "default"`) retry a safety-declined request
  on a suitable model; effort is set to `medium`. A remaining refusal returns
  `422 assistant_declined`. **OpenAI:** requests use `store=false`.
- It is instructed to answer only from that summary and to say when something
  (e.g. predictions or profit) is not available.
- Provider failures map to clear errors: `assistant_auth_failed`,
  `assistant_quota_exceeded`, `assistant_rate_limited`, `assistant_timeout`,
  `assistant_unreachable`, `assistant_model_not_found`.
- Questions and answers are never logged; only timings and turn counts.
- Tests use a fake model, so running them costs nothing.

## Error format

Every error response uses:

```json
{"error": {"code": "not_found", "message": "Not Found", "details": null}}
```

Validation errors list the field locations and reasons, never the submitted values.

## Database schema

| Table | Contents |
| --- | --- |
| `customers` | One row per `customer_id` from imports (email, optional name/country). |
| `orders` | One row per imported order: date, value, optional category/channel, optional `engagement_score` (0–100; NULL means not provided — never treated as 0). |
| `import_jobs` | Each uploaded file: status, row counts, row-level errors (no customer values). |

Create a new migration after changing models:

```powershell
.\.venv\Scripts\alembic.exe revision --autogenerate -m "describe change"
```
