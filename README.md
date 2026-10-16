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
| Churn probability, predicted CLV, 3-month revenue forecast | ✅ Trained models (scikit-learn), **shown only if they pass an accuracy test** on data they were not trained on. Otherwise "Not available" with the reason. Details below. |
| Growth Score | ✅ Our own 0-100 score from four measured metrics (revenue growth, retention, average health, customer growth). The page shows the inputs and weights; it is not an industry standard and not a prediction. Needs about 6 months of history. |
| Revenue at Risk calculator | ✅ A "what if" tool that starts from your At-Risk and Lost customers |
| Sign-in (accounts, sessions, change password) | ✅ Built. In live mode every page and API call needs a signed-in user. Demo mode has no sign-in. |
| Public real-world test dataset (UCI Online Retail II) | ✅ Converter included (see "Test data") |
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

## Quick start on Windows (after the first-time setup)

1. Close any old CustomerIQ terminals or black windows (so ports 8000 and 3001 are free).
2. **Double-click `start-customeriq.bat`** in the project folder.
3. Two black windows open (the backend and the website) and your browser opens at
   <http://localhost:3001>. Keep the black windows open while you use the app.
4. To stop the app, close the two black windows.

If it says a port is "already in use", something is still running: close the old windows
and try again. Run `start-customeriq.bat check` to test the setup without starting anything.
The rest of this section explains the same thing by hand, with terminals.

## Run the app by hand (every time)

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

## Signing in

In live mode the site shows a **sign-in page** first. Nothing about your customers
is visible, and the API refuses every request, until someone is signed in.

- **First time:** open the site. With no accounts yet it shows **Create your
  account**: your name, email and a password (10+ characters; a few unrelated
  words like "blue tractor sings loudly" work well). You are signed in straight away.
- **Real emails only (optional):** put your email settings in `backend/.env` (see `SMTP_*` in
  `backend/.env.example`; for Gmail you need an **App Password**). Then every new account, including
  yours, must type a **6-digit code** that is emailed to it before it can sign in, and a
  **Create an account** link appears so other people can sign up. Without email settings, accounts
  are created without a code and only the owner account can be created on the site. All signed-in
  users see the same data, so do not enable public sign-up for confidential data.
- **Later:** **Sign in** with that email and password. "Keep me signed in on this
  device" keeps you signed in for 30 days; without it the session ends after 24 hours
  or when you close the browser.
- **Your account** (avatar menu, top right): see your details, **change your
  password** (other devices are signed out), or **Sign out**.
- **More people / forgotten password:** use the command-line tool (passwords are
  typed at a hidden prompt):

```powershell
cd D:\CustomerIQ.AI\backend
.\.venv\Scripts\python.exe scripts\manage_users.py list
.\.venv\Scripts\python.exe scripts\manage_users.py create teammate@company.com --name "Teammate"
.\.venv\Scripts\python.exe scripts\manage_users.py reset-password you@company.com
.\.venv\Scripts\python.exe scripts\manage_users.py deactivate former@company.com
```

How it is protected: passwords are stored only as scrypt hashes; the session cookie
is `HttpOnly` (page scripts cannot read it) and `SameSite=Lax`; only a hash of the
session token is stored; 8 wrong attempts lock that email for 15 minutes; writes from
other websites are refused. Demo mode (no backend address) has no sign-in.

> **Before putting the site on the internet:** set `APP_ENV=production` (secure
> cookies, hides the API docs) and a `SETUP_CODE` in `backend/.env`, so a stranger who
> finds the site first cannot create the owner account. Use HTTPS. There is one kind of
> account (everyone sees everything); roles are not built.

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

### Predictions (trained models)

Three models retrain **automatically whenever your imported data changes**:

| Model | What it estimates | Needs at least |
| --- | --- | --- |
| Churn probability | The chance a customer places **no order in the next 90 days** | ~9 months of orders and 200+ customers with history 6 months ago |
| Predicted CLV | Revenue to date **plus** estimated spend over the next 6 months | ~15 months of orders and 200+ customers with history 12 months ago |
| Revenue forecast | The next 3 months, with an 80% range (straight-line trend, no seasonality) | 12+ complete months of orders |

How they are kept honest:

- Each model learns from an **older period** and is **tested on a later period it
  never saw**. The test results appear next to the predictions (the blue
  "model estimates, not facts" note).
- A model is shown only if it beats a simple rule of thumb (for churn: "longer
  since last order = riskier"; for CLV: "spend what you spent in the last 6
  months"; for the forecast: "repeat the recent average"). Otherwise the page
  says why it is not available.
- Missing engagement is never treated as zero.
- Predictions are **estimates**. They are only as good as the data: models
  trained on the synthetic test data prove the code works, nothing more.

### Public real-world test data (recommended for trying the predictions)

No store of your own? The public **Online Retail II** dataset has real orders from a
UK online shop: about 36,600 orders from 5,850 customers over two years. Credit the
source if you share results (licence **CC BY 4.0**): Chen, D. (2019). *Online Retail II*
[Dataset]. UCI Machine Learning Repository. <https://doi.org/10.24432/C5CG6D>

1. Download `online+retail+ii.zip` from the dataset page
   (<https://archive.ics.uci.edu/dataset/502/online+retail+ii>, 43 MB; the server is slow
   and sometimes drops the connection, so retry if the zip is incomplete) and unzip
   `online_retail_II.xlsx` into its **own empty folder** (it is untrusted data).
2. Convert it (one row per invoice, guest checkouts and cancellations skipped, the
   overlapping December 2010 rows counted once; see the script's header for every rule):

```powershell
cd D:\CustomerIQ.AI\backend
.\.venv\Scripts\python.exe -I scripts\convert_uci_online_retail.py "C:\path\to\online_retail_II.xlsx"
```

3. Remove the synthetic data (below), then upload `data\public_uci_online_retail_ii.csv`
   on the Import page. Its IDs start with `PUB-`; remove it later with
   `delete_synthetic_data.py --source public`.

Things to know: amounts are in **pounds** (the app shows a $ symbol); the dataset has no
product categories, names, emails (placeholders `pub-<id>@example.com`) or engagement;
and it is a gift wholesaler with a big Christmas peak. On it, the **churn model is
accepted** (AUC 0.80 vs 0.76 for the simple rule), while **predicted CLV and the
forecast are honestly declined** because they did not beat their simple baselines.

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

Only rows whose IDs start with `SYN-` are deleted. (Add `--source public` to remove
the public dataset's `PUB-` rows instead.)

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

## Putting it on the internet (optional)

You do **not** need this to use the app on your own computer. If you ever want it online,
here is a step-by-step guide (GitHub, Supabase, Railway, Vercel): [`docs/DEPLOY.md`](docs/DEPLOY.md).

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
| You are sent to the **sign-in page** again and again | Your session ended (24 hours, or you signed out elsewhere), or the browser blocks cookies for this site. Sign in again; check cookies are allowed. |
| **"That email or password is not correct."** | Check the email and password (the email ignores capital letters). After 8 wrong tries the email is locked for about 15 minutes. |
| **"Too many sign-in attempts"** | Wait the number of minutes shown. A forgotten password can be reset with `manage_users.py reset-password`. |
| Sign-in page says **"We can't reach the server"** | The backend is not running. Start Terminal 1 and click **Try again**. |
| Pages say **Couldn't load live data** | The backend is not running or not reachable. Start Terminal 1, then click **Try again**. |
| Health check shows `"database": "unavailable"` | PostgreSQL is stopped or `DB_PASSWORD` in `backend/.env` is wrong. Details are in the backend terminal. |
| Assistant says **AI not configured** | Add `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY` with `AI_PROVIDER=openai`) to `backend/.env` and restart the backend. |
| Assistant says **no remaining credits** | Add API credits in the Claude Console (Billing) — a Claude Pro subscription does not include API credits. |
| Build fails with `Failed to fetch Geist from Google Fonts` | The build downloads fonts; check the internet connection and run it again. |

## Project layout

```text
backend/
  app/api/v1/        HTTP endpoints (health, auth, imports, analytics, assistant)
  app/services/      import checks, analytics formulas, predictions, AI assistant, sign-in
  app/models/        database tables;  alembic/ = migrations
  scripts/           test-data generator/converter, cleanup, manage_users.py
  tests/             pytest suite
frontend/
  proxy.ts           sends visitors without a sign-in cookie to /login
  app/               pages (one folder per page; login/ and account/ for sign-in)
  components/        UI components and charts
  lib/api/           API client; demo/live switch
  lib/mock/          sample data used only in demo mode
docs/specification.pdf
data/                local data files (gitignored)
```
