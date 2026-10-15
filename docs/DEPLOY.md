# Putting CustomerIQ AI on the internet (free: Vercel + Supabase)

> **Optional.** The app runs fine on your own computer with `start-customeriq.bat` (see the
> README). Follow this guide only if you want a public website. It needs **no credit card**.

You will end up with three parts, all free for personal projects:

```text
 Browser ──▶ Vercel project 1: the website ──forwards /api/…──▶ Vercel project 2: the API ──▶ Supabase database
                                  ▲                                      ▲
                                  └──── both are built from your GitHub repository ────┘
```

Screens change over time, so a button may look slightly different. The *ideas* (what to
create and which values to copy where) stay the same.

## 0. What you need before you start

| You need | Notes |
| --- | --- |
| **GitHub** repository with the latest code | The code must be pushed (step 1). |
| **Supabase** project | You already created `customeriq`. Keep its 5 connection values (host, port, database, user, password) in a private note. |
| **Vercel** account | Sign up with GitHub. The free *Hobby* plan is for personal, non-commercial use. |
| A **setup code** | Invent one (three random words). It protects "Create your account" on the public site. |

**Golden rules**

- **Never** paste a password or key into a chat, a GitHub file, or an email. Type or paste
  them only into the service's own settings page.
- Use the **public test dataset** first (see the README), not real customer data. Free
  hosting is not meant for confidential business data.

## 1. Push the latest code to GitHub

In VS Code open **Source Control** and click **Sync Changes**. Then open your repository on
github.com and check that `backend`, `frontend` and `docs` are there and that no `.env` file is.

## 2. Create the tables in Supabase (once)

On your own computer, in the `backend` folder:

```powershell
cd D:\CustomerIQ.AI\backend
.\.venv\Scripts\python.exe scripts\migrate_remote.py
```

It asks for the **host**, **port**, **database**, **user** and **password** (the password is
typed hidden and never saved). It shows where it is about to write and waits for you to type
`YES`. At the end it lists the tables: `customers`, `import_jobs`, `orders`, `sessions`,
`users`, `alembic_version`. Run it again after any future update that changes the database.

## 3. Deploy the API (Vercel project 1)

1. In Vercel: **Add New → Project**, then import your `customeriq-ai` repository.
2. Set **Root Directory** to **`backend`**. Vercel detects **FastAPI** by itself.
3. Open **Environment Variables** and add these (paste the values yourself):

   | Name | Value |
   | --- | --- |
   | `DB_HOST` | your Supabase host (contains `pooler.supabase.com`) |
   | `DB_PORT` | `5432` |
   | `DB_NAME` | `postgres` |
   | `DB_USER` | your Supabase user (like `postgres.abcdefghij`) |
   | `DB_PASSWORD` | your Supabase database password |
   | `DB_SSLMODE` | `require` |
   | `DB_POOL_SIZE` | `1` |
   | `DB_MAX_OVERFLOW` | `1` |
   | `APP_ENV` | `production` |
   | `SETUP_CODE` | your invented setup code |
   | `FRONTEND_ORIGINS` | `https://placeholder.example` (you set the real value in step 5) |

   Optional: `ANTHROPIC_API_KEY` (needs paid API credits; without it the assistant says "AI not configured").
4. Click **Deploy**. When it finishes, copy the project's address, for example
   `https://customeriq-api.vercel.app` (use the **production domain**, not a long preview link).
5. Open `<that address>/api/v1/health`. You should see `{"status":"ok","database":"ok"}`.

If Vercel shows its own sign-in page instead: open the API project → **Settings → Deployment
Protection** and turn **Vercel Authentication** off for production, then try again.

## 4. Deploy the website (Vercel project 2)

1. **Add New → Project**, import the **same** repository again.
2. Set **Root Directory** to **`frontend`** (Next.js is detected).
3. Add one environment variable:

   | Name | Value |
   | --- | --- |
   | `NEXT_PUBLIC_API_BASE_URL` | the API address from step 3.4, **no trailing slash** |

   This is baked in when the site is built: if you change it later, **redeploy** the website.
4. Click **Deploy**, and copy the website's address, for example `https://customeriq.vercel.app`.

## 5. Connect the two

The API only accepts requests from your website. In the **API project → Settings → Environment
Variables**, change `FRONTEND_ORIGINS` to the website address exactly (for example
`https://customeriq.vercel.app`, no trailing slash, no path). Then **redeploy the API**
(**Deployments →** the latest one **→ Redeploy**), because changes only apply to new deployments.

## 6. First run

1. Open the website address. You land on **Create your account**: enter your name, email, a
   password (10+ characters) and the **setup code**. You are signed in.
2. Go to **Import Data** and upload `public_uci_online_retail_ii.csv` (see the README; about
   3.3 MB). Open the dashboards.
3. Anyone else who visits sees only the sign-in page. After your account exists, the setup form
   no longer works.

## Good to know

- **Region:** both projects run in Singapore (`sin1`, set in `backend/vercel.json` and
  `frontend/vercel.json`) because that is where we suggested creating Supabase. If your Supabase
  project is elsewhere, change both files to the nearest Vercel region (for example `bom1` Mumbai,
  `fra1` Frankfurt, `iad1` Washington), push, and redeploy. A wrong region only makes it slower.
- **Free limits:** a request body can be at most **4.5 MB** on Vercel, so CSV files above that
  fail to upload (the public test file is 3.3 MB; split bigger files). Supabase free projects
  **pause after a week without use**; open the Supabase dashboard to resume. Hobby is for
  personal, non-commercial use only.
- **Slow first load:** the API starts on demand, so the first visit after a quiet spell can take
  a few seconds.
- **Updating:** push to GitHub and Vercel rebuilds both projects by itself. If an update changes
  the database, run `migrate_remote.py` again.
- **Passwords and accounts:** teammates and password resets use `manage_users.py`; point it at the
  hosted database the same way as `migrate_remote.py` (ask for help before doing this).

## Troubleshooting

| You see | Likely cause and fix |
| --- | --- |
| `/api/v1/health` says `"database":"unavailable"` | A `DB_*` value is wrong (host must contain `pooler.supabase.com`), the tables were not created (step 2), or the Supabase project is paused. |
| Vercel build of the API fails on install | Check the build log; the project needs Python 3.13 (set by `backend/.python-version`). Tell me the last lines of the log. |
| The site says **"We couldn't reach the server"** | `NEXT_PUBLIC_API_BASE_URL` is missing or wrong (then redeploy the website), or the API address answers with a Vercel sign-in page (see step 3). |
| Sign-in works, then you are sent back to sign in | The API is not in production mode, or the website address is not exactly `FRONTEND_ORIGINS`. |
| *"This request came from a website that is not allowed"* | `FRONTEND_ORIGINS` does not match the address in the browser bar. Fix it and redeploy the API. |
| **"That setup code is not correct"** | Use the value of `SETUP_CODE` from the API project's settings. |
| CSV upload fails on the live site only | The file is over 4.5 MB (see "Free limits"). |
| The assistant says **no remaining credits** | Add API credits in the Claude Console (a Claude Pro subscription does not include them). |

## Security checklist before real customer data

- [ ] The GitHub repository is **private**.
- [ ] `APP_ENV=production` and a `SETUP_CODE` are set on the API project.
- [ ] You created the first account yourself and confirmed "Create your account" no longer appears.
- [ ] No keys or passwords are in the repository.
- [ ] You have the right to use your customers' data, and you are not on a plan that forbids business use (Vercel Hobby is non-commercial).
