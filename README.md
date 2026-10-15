# CustomerIQ AI

AI-powered customer intelligence dashboard for e-commerce stores: import your
orders, then see segments, health scores, inactivity, revenue trends,
recommendations, and ask an AI assistant about your data.

| Part | Technology | Folder |
| --- | --- | --- |
| Frontend | Next.js 16, TypeScript, Tailwind CSS, Recharts | [`frontend/`](frontend/) |
| Backend API | Python 3.13, FastAPI | [`backend/`](backend/) |
| Database | PostgreSQL 18 | (local service) |
| AI assistant | Anthropic Claude API (default) or OpenAI (optional) | `backend/app/services/assistant.py` |

The project specification is in [`docs/specification.pdf`](docs/specification.pdf).

## What is real and what is not yet

| Feature | Status |
| --- | --- |
| CSV / Excel (.xlsx) import with row validation | ✅ Real, server-side |
| Dashboard KPIs, RFM segments, health scores, revenue trends and drivers | ✅ Calculated from your data with fixed formulas |
| Inactivity levels, revenue at risk, recommendations, executive summary | ✅ Rule-based (described as such in the UI) |
| AI Business Assistant | ✅ Real once `ANTHROPIC_API_KEY` is set; answers only from your summary figures |
| Churn probability, predicted CLV, revenue forecast, growth score | ⏳ Not available — needs trained models (Phase 4). Shown as "Not available yet". |
| Sign-in / user accounts | ⏳ Not built. The header shows a "Demo workspace" placeholder. |
| Shopify orders export (CSV) | ✅ Detected automatically and converted on the server |
| Shopify / WooCommerce API sync | ⏳ Not built. Use the Shopify CSV export (or a standard CSV) for now. |

## Demo mode vs live mode

- **Demo mode:** no backend address is configured. Every page shows clearly
  labelled **sample data** (yellow "Demo data" badge). Nothing is uploaded.
- **Live mode:** `frontend/.env.local` contains `NEXT_PUBLIC_API_BASE_URL`.
  Pages show your imported data (green "Live data" badge). If the backend is
  down, pages show an error with **Try again** — never sample data.

---

## First-time setup

Do this once. You need Python 3.13, Node.js, and PostgreSQL 18 installed.

### 1. Database (PostgreSQL)

Create a database `customeriq` owned by a login `customeriq_app` that has no
admin rights. In **SQL Shell (psql)** as the `postgres` user:

```sql
CREATE ROLE customeriq_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
\password customeriq_app
CREATE DATABASE customeriq OWNER customeriq_app;
REVOKE ALL ON DATABASE customeriq FROM PUBLIC;
```

### 2. Backend

PowerShell (`PS D:\...>` prompt):

```powershell
cd D:\CustomerIQ.AI\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Bash (`$` prompt):

```bash
cd /d/CustomerIQ.AI/backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
cp .env.example .env
```

Then open `backend/.env` in VS Code and set the database password, inside
single quotes: `DB_PASSWORD='your-app-password'`. Then create the tables:

```powershell
.\.venv\Scripts\alembic.exe upgrade head        # PowerShell
./.venv/Scripts/alembic.exe upgrade head        # Bash
```

> `backend/.env` holds secrets. It is gitignored — never commit it or paste it anywhere.

### 3. Frontend

```powershell
cd D:\CustomerIQ.AI\frontend
npm.cmd install                                   # PowerShell: use npm.cmd
Copy-Item .env.example .env.local                 # live mode (backend at 127.0.0.1:8000)
```

In Bash use `npm install` and `cp .env.example .env.local`. Skip the copy to
run in demo mode.

---

## Run the app (every time)

Open **two terminals** in VS Code (Terminal → New Terminal, then **+**).

### Terminal 1 — backend

| PowerShell | Bash |
| --- | --- |
| `cd D:\CustomerIQ.AI\backend` | `cd /d/CustomerIQ.AI/backend` |
| `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000` | `./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000` |

Wait for `Application startup complete`. Check: <http://127.0.0.1:8000/api/v1/health>
should show `{"status":"ok","database":"ok"}`. API docs: <http://127.0.0.1:8000/docs>

### Terminal 2 — frontend

| PowerShell | Bash |
| --- | --- |
| `cd D:\CustomerIQ.AI\frontend` | `cd /d/CustomerIQ.AI/frontend` |
| `npm.cmd run dev` | `npm run dev` |

Open the address it prints (usually <http://localhost:3000>, or **3001** if
port 3000 is already used by another project).

Stop either server with **Ctrl+C** in its terminal.

---

## Using it

1. Go to **Import Data**, choose a CSV or .xlsx file (one row per order), and
   click **Import customers**. Required columns:
   `customer_id, email, order_id, order_date, order_value`. Optional:
   `first_name, last_name, country, product_category, channel, engagement`.
   Click **CSV template** for an example.
2. Open the dashboards. Segments need at least 20 customers; retention and
   comparisons need at least 180 days of history.
3. Re-uploading a file is safe: existing order IDs are updated, not duplicated.

### Importing from Shopify

In Shopify Admin go to **Orders → Export**, choose the orders (or all), and
export as **Plain CSV file**. Upload that file unchanged on the Import page —
it is recognised automatically:

- Shopify writes one row per product line; rows are grouped into one order each.
- Shopify has no customer ID column, so the customer's **email** is their ID.
  Orders without an email (e.g. some POS sales) are rejected and listed.
- Canceled, voided, and fully refunded orders are **skipped** and listed.
  Partially refunded orders count `Total − Refunded Amount`.
- Shopify exports do not include product categories or engagement, so those
  dashboard parts show "Not specified" / use the re-weighted health score.

### Test data (synthetic)

`backend/scripts/generate_demo_data.py` creates a **made-up** file
(`data/demo_orders_synthetic.csv`, 300 customers, IDs start with `SYN-`) for
trying the app. Its numbers are not real business results. Before importing
real data, remove it:

```powershell
cd D:\CustomerIQ.AI\backend
.\.venv\Scripts\python.exe scripts\delete_synthetic_data.py --dry-run   # shows counts only
.\.venv\Scripts\python.exe scripts\delete_synthetic_data.py             # type DELETE to confirm
```

Only rows whose IDs start with `SYN-` are deleted.

### Turning on the AI assistant (optional)

The assistant uses **Claude** (Anthropic) by default.

1. Create an API key in the **Claude Console** at <https://platform.claude.com>
   (API keys page). API usage is billed separately from Claude Pro / Max
   subscriptions, so the account needs **API credits** (Billing page).
2. Add to `backend/.env` (type the key yourself; never share it):

   ```dotenv
   AI_PROVIDER=anthropic
   ANTHROPIC_API_KEY='your-key'
   ANTHROPIC_MODEL=claude-opus-5-5
   ```

   To use OpenAI instead: `AI_PROVIDER=openai`, `OPENAI_API_KEY='your-key'`,
   `OPENAI_MODEL=gpt-6-luna`.

3. Restart the backend (Ctrl+C, then start it again).

The assistant only sees summary figures and anonymous customer IDs — never
names or emails.

---

## Checks

```powershell
# Backend tests (use a rolled-back transaction; your data is not changed; no AI credits used)
cd D:\CustomerIQ.AI\backend
.\.venv\Scripts\python.exe -m pytest

# Frontend type check, lint, production build
cd D:\CustomerIQ.AI\frontend
npx.cmd tsc --noEmit
npm.cmd run lint
npm.cmd run build
```

---

## Troubleshooting

| You see | Cause and fix |
| --- | --- |
| `npm.ps1 cannot be loaded because running scripts is disabled` | PowerShell blocks `npm.ps1`. Use **`npm.cmd`** (and `npx.cmd`) instead. No security change needed. |
| `bash: cd: D:CustomerIQ.AIbackend: No such file` | Bash removes `\`. Use `/d/CustomerIQ.AI/backend` with forward slashes. |
| `Could not read package.json` at `D:\package.json` | You are in the wrong folder. Run the `cd` line first, then check with `pwd`. |
| `EPERM: operation not permitted` / build lockfile errors | The folder is not writable for your user. In an **administrator** PowerShell: `icacls "D:\CustomerIQ.AI" /grant "${env:USERNAME}:(OI)(CI)M" /T`. |
| Port 3000 is in use | Another project is running. Next.js picks 3001 automatically; use that address. |
| Pages say **Couldn't load live data** | The backend is not running or not reachable. Start Terminal 1, then click **Try again**. |
| Health check shows `"database": "unavailable"` | PostgreSQL is stopped or `DB_PASSWORD` in `backend/.env` is wrong. Details are in the backend terminal. |
| Assistant says **AI not configured** | Add `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY` with `AI_PROVIDER=openai`) to `backend/.env` and restart the backend. |
| Assistant says **no remaining credits** | Add API credits in the Claude Console (Billing) — a Claude Pro subscription does not include API credits. |
| Build fails with `Failed to fetch Geist from Google Fonts` | The build downloads fonts; check the internet connection and run it again. |

## Project layout

```text
backend/
  app/api/v1/        HTTP endpoints (health, imports, analytics, assistant)
  app/services/      import checks, analytics formulas, AI assistant
  app/models/        database tables;  alembic/ = migrations
  scripts/           synthetic data generator and cleanup
  tests/             pytest suite
frontend/
  app/               pages (one folder per page)
  components/        UI components and charts
  lib/api/           API client; demo/live switch
  lib/mock/          sample data used only in demo mode
docs/specification.pdf
data/                local data files (gitignored)
```
