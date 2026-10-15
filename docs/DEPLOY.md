# Putting CustomerIQ AI on the internet

> **Optional.** The app runs fine on your own computer with `start-customeriq.bat` (see the
> README). This guide is only for the day you want a public website. It was written for
> Railway, but a free combination (Vercel for the site, Render for the API, Supabase for the
> database) also works: use the backend's `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
> `DB_PASSWORD` and `DB_SSLMODE=require` settings instead of building a `DATABASE_URL`.

This guide takes the app from your computer to a public website, step by step. Three
services each run one part, and **GitHub** holds the code that feeds them:

```text
 You → Vercel (website) ──forwards /api/…──▶ Railway (Python API) ──▶ Supabase (database)
                 ▲                                   ▲
                 └──────── both rebuild from your GitHub repository ────────┘
```

Screens change over time, so button names below may look slightly different. The
*ideas* (what to create, which values to copy where) stay the same.

## 0. Before you start

| You need | Notes |
| --- | --- |
| A **GitHub** account | Connected to VS Code. |
| A **Supabase** account | Free plan is enough to start. Hosts the PostgreSQL database. |
| A **Railway** account | Hosts the Python API. It has a short free trial, then a small monthly cost: check its pricing page. A card may be needed. |
| A **Vercel** account | "Hobby" plan is free for personal projects. Hosts the website. Sign up with GitHub. |
| About 45 minutes | |

**Golden rules while doing this**

- **Never** paste a password, API key or database address into a chat, a GitHub file or
  an email. Type or paste them only into the service's own settings page (Railway,
  Vercel) as instructed.
- Use a **password manager** (or paper) for the database password. Supabase shows it
  once.
- Deploy with the **public test dataset first** (see the README), not real customer data.

## 1. Publish the code to GitHub (private)

1. In VS Code open **Source Control** (the branch icon on the left).
2. Click **Publish to GitHub** (or press `Ctrl+Shift+P` and run *Git: Publish to GitHub*).
3. Name it `customeriq-ai` and choose **Private repository**. Keep `docs/`, `backend/`
   and `frontend/` ticked, and leave `.env` files unticked if VS Code lists them (they
   are ignored by git and never uploaded).
4. Open the repository on github.com and check the file list: you should see
   `backend`, `frontend`, `docs`, `README.md` and **no** `.env` file and **no** `data`
   folder.

*Why private?* Every commit carries your name and email, and a private repo keeps them
(and the project) out of public view. You can still give Vercel and Railway access.

## 2. Database (Supabase)

1. Create a new **project** (name `customeriq`, choose a region near you). Set a **strong
   database password** and save it in your password manager.
2. Wait until the project is ready, then click **Connect** (top of the project page).
3. Choose the **Session pooler** connection string (it works on every network). It
   looks like `postgresql://postgres.xxxx:[YOUR-PASSWORD]@aws-0-…pooler.supabase.com:5432/postgres`.
4. Prepare it for the app. In a private note (not in the repo):
   - replace `[YOUR-PASSWORD]` with the real password;
   - change the start `postgresql://` to **`postgresql+psycopg://`**;
   - add `?sslmode=require` at the very end.
5. Keep this finished address handy: it becomes the `DATABASE_URL` in step 3.

## 3. The API (Railway)

1. **New Project → Deploy from GitHub repo** and pick `customeriq-ai`. Allow Railway
   to read the repository when asked.
2. Open the service's **Settings**:
   - **Root Directory**: `backend`
   - **Start Command**:
     `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
     (the first part creates or updates the database tables, the second starts the API)
   - **Healthcheck path** (if offered): `/api/v1/health`
3. Open **Variables** and add these (paste the values yourself):

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | the finished address from step 2 |
   | `APP_ENV` | `production` |
   | `SETUP_CODE` | a code you invent, e.g. three random words. Needed once, to create the first account |
   | `FRONTEND_ORIGINS` | leave for now; you set it in step 5 |
   | `ANTHROPIC_API_KEY` | optional: your Claude key, for the AI assistant (needs API credits) |
   | `AI_PROVIDER` | `anthropic` (default) |

4. **Settings → Networking → Generate Domain** to get the API's public address
   (something like `https://customeriq-api-production.up.railway.app`).
5. Open `<that address>/api/v1/health` in your browser. You should see
   `{"status":"ok","database":"ok"}`. If `database` says `unavailable`, re-check
   `DATABASE_URL` (password, the `+psycopg`, the `?sslmode=require`).

If the build uses an old Python version, add the variable `NIXPACKS_PYTHON_VERSION` =
`3.13` (the repo also contains `backend/.python-version`).

## 4. The website (Vercel)

1. **Add New → Project**, import `customeriq-ai`.
2. Set **Root Directory** to `frontend` (framework: Next.js is detected).
3. Under **Environment Variables** add:

   | Variable | Value |
   | --- | --- |
   | `NEXT_PUBLIC_API_BASE_URL` | the Railway address from step 3.4, **no trailing slash** |

   This value is baked in when the site is built. If you change it later, **redeploy**.
4. Click **Deploy**. When finished, Vercel shows the site's address, e.g.
   `https://customeriq-ai.vercel.app`.

## 5. Connect the two (one more setting)

The API must know which website is allowed to talk to it.

1. Back in Railway → **Variables**, set `FRONTEND_ORIGINS` to the exact Vercel address,
   for example `https://customeriq-ai.vercel.app` (no trailing slash, no path).
2. Railway redeploys automatically.

*(Preview addresses that Vercel makes for branches are different websites, so they are
refused on purpose. Use the main address.)*

## 6. First run

1. Open your Vercel address. You land on **Create your account**.
2. Enter your name, email, a password (10+ characters), and the **setup code** from step
   3. You are signed in.
3. Go to **Import Data** and upload `public_uci_online_retail_ii.csv` (see the README
   for how to create it; it is about 3.3 MB). Check the dashboards fill in.
4. Anyone who opens the address now sees the sign-in page and nothing else. Once you
   have your account, the setup form no longer works.
5. To add a teammate or reset a password, use the Railway service's shell or run
   `manage_users.py` on your own computer **with `DATABASE_URL` pointing at the same
   database** (see the README).

## 7. After it is live

- **Updating:** commit and push in VS Code. Vercel and Railway rebuild by themselves.
- **Cost watch:** check the Railway usage page now and then; Vercel Hobby and Supabase
  free plans have limits (free Supabase projects can pause after a week of inactivity).
- **Real data:** only after you are happy with the test run, delete the test data
  (`delete_synthetic_data.py --source public`) and import your own export. Anyone
  with an account sees all data; roles are not built.
- **AI assistant:** needs `ANTHROPIC_API_KEY` and API credits. Without them it says
  "AI not configured".

## Troubleshooting

| You see | Likely cause and fix |
| --- | --- |
| Railway build fails on `pip install` | Python version: set `NIXPACKS_PYTHON_VERSION=3.13` and redeploy. |
| `/api/v1/health` says `"database":"unavailable"` | `DATABASE_URL` is wrong: check password, `postgresql+psycopg://`, `?sslmode=require`, and that the Supabase project is not paused. |
| The site says **"We can't reach the server"** | `NEXT_PUBLIC_API_BASE_URL` is missing or wrong (then redeploy Vercel), or the Railway service is down. |
| Sign-in works but you bounce back to the sign-in page | The API is not in production/HTTPS mode, or the Vercel address is not in `FRONTEND_ORIGINS`. |
| Errors like *"This request came from a website that is not allowed"* | `FRONTEND_ORIGINS` does not exactly match the address in the browser bar. |
| **"That setup code is not correct"** | Use the value of `SETUP_CODE` from Railway exactly. |
| Uploading a CSV fails on the live site but works on your computer | Large uploads pass through Vercel, which may limit request size (about 4.5 MB). The public test file (3.3 MB) fits; for bigger files split the CSV or tell me and we will add a direct upload route. |
| The assistant says **no remaining credits** | Add API credits in the Claude Console. A Claude Pro subscription does not include them. |

## Security checklist before real customer data

- [ ] The GitHub repository is **private**.
- [ ] `APP_ENV=production` and a `SETUP_CODE` are set on Railway.
- [ ] You created the first account yourself, then confirmed `Create your account` no longer appears.
- [ ] No keys or passwords are in the repository (`git log` has none; the `.env` files stay local).
- [ ] Your customers know their data is processed here, and you have the right to use it.
