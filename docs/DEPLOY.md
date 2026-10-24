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
`yes`. At the end it lists the tables: `customers`, `import_jobs`, `orders`, `sessions`,
`users`, `alembic_version`. **Run it again after any update that changes the database**: the
email-verification update added columns to `users`, so run it before deploying that version.

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
   | `MAIL_WEBHOOK_URL` | the address of your mail relay (see "Email codes" below; leave the email variables out to skip email) |
   | `MAIL_WEBHOOK_SECRET` | the secret you chose inside the mail relay script |
   | `FRONTEND_ORIGINS` | `https://placeholder.example` (you set the real value in step 5) |

   Optional: `ANTHROPIC_API_KEY` (needs paid API credits; without it the assistant says "AI not configured").
4. Click **Deploy**. When it finishes, copy the project's address, for example
   `https://customeriq-api.vercel.app` (use the **production domain**, not a long preview link).
5. Open `<that address>/api/v1/health`. You should see `{"status":"ok","database":"ok"}`.

If Vercel shows its own sign-in page instead: open the API project → **Settings → Deployment
Protection** and turn **Vercel Authentication** off for production, then try again.

### Email codes (so people must use a real email address)

When the `SMTP_*` variables are set, every new account must **confirm its email address** with a
6-digit code before it can sign in, and **anyone with a real email address can create an account**
(set `ALLOW_SIGNUP=false` on the API project to turn public sign-up off again). Without them, accounts
are created without a code and only the owner account can be created on the site.

**On Vercel, send through your own Gmail with a small Google script (free, no card, no other company).**
Vercel's servers cannot reach mail servers (SMTP, for example Gmail's) and fail with
`OSError, error 99`. A Google Apps Script "web app" sends the email from your Gmail over HTTPS, which
always works. Gmail lets a normal account send about 100 emails a day this way, plenty for sign-up codes.

1. Open <https://script.google.com> signed in as the Gmail that should send the codes, and click **New project**.
2. Delete the sample code and paste the whole of [`docs/mail-relay.gs`](mail-relay.gs).
3. On the line starting `const SECRET`, replace the text with your own secret (a few random words, no
   spaces). Keep a copy: you need it in step 7. Click **Save**.
4. In the function list above the editor choose **`authorize`** and click **Run**. Google asks for
   permission: **Review permissions** → your account → **Advanced** → **Go to … (unsafe)** → **Allow**.
   ("Unsafe" only means Google has not reviewed your own script.)
5. Click **Deploy → New deployment**, the gear icon → **Web app**. Set **Execute as: Me** and
   **Who has access: Anyone**, then **Deploy**.
6. Copy the **Web app URL** (it ends in `/exec`). Opening it in a browser should show
   `{"ok":true,"service":"CustomerIQ mail relay"}`.
7. On the API project add `MAIL_WEBHOOK_URL` (that URL) and `MAIL_WEBHOOK_SECRET` (your secret), then
   **redeploy the API**. The secret is the only thing that lets someone send mail through the script, so
   keep it out of chats and the repository.

If you change the script later, use **Deploy → Manage deployments → edit → New version**, so the address stays the same.

**Alternatives.** Brevo's HTTPS API (`BREVO_API_KEY` + `MAIL_FROM`) works too if your account allows it.
**On your own computer** you can use Gmail SMTP (turn on 2-Step Verification, create an App Password at
<https://myaccount.google.com/apppasswords>) with `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`,
`SMTP_USER` and `SMTP_PASSWORD` in `backend/.env`. If several are set, the mail relay is used first, then
Brevo, then SMTP.

Codes expire after 15 minutes,
allow 5 wrong tries, and one address can be sent at most one code a minute and 5 an hour.

> **Important:** the app shows **one shared set of customer data to every signed-in user**; accounts do
> not get separate data. With public sign-up on, anyone who confirms an email can see everything you
> imported. Use **public test data only** (or set `ALLOW_SIGNUP=false` and create teammates yourself with
> `manage_users.py`) before importing real customers.

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

## Optional: screenshots in Launch Studio

The Competitor Board can keep a screenshot with each saved ad. Everything else works without this.

1. In Supabase open **Storage** and click **New bucket**. Name it `competitor-ads` and leave **Public bucket** OFF.
2. In Supabase open **Project Settings > API**. Copy the project URL and the **service_role** key.
3. In the **API** project on Vercel add `SUPABASE_URL` (the project URL) and `SUPABASE_SERVICE_KEY` (the service_role key),
   then redeploy the API. Never add the service key to the website project.

Screenshots are PNG, JPEG or WebP, at most 3 MB, and are shown through links that stop working after an hour.

## Optional: Auto Messenger (WhatsApp and email)

Everything works **without** setting any of this: messages are only recorded (a "dry run"), so you can try every page
for free. Do the steps below only when you want to really send.

**Always first.** In the API project on Vercel add `MESSAGING_DRY_RUN` = `true`, a long random `MESSAGING_SECRET`, and
`PUBLIC_API_URL` (the API address, no slash at the end). Then run `migrate_remote.py` (the new tables).

**WhatsApp (Meta's official Cloud API).**
1. At developers.facebook.com create an app (type *Business*) and add the **WhatsApp** product. Meta gives you a free
   *test phone number*. In *API Setup* add your own phone as a recipient (the test number can only message people you add).
2. Copy the **Phone number ID** and the **temporary access token** into `WHATSAPP_PHONE_NUMBER_ID` and `WHATSAPP_ACCESS_TOKEN`.
   (A temporary token lasts about a day; for lasting use create a *system user* token in Meta Business settings.)
3. Copy the app secret (*App settings > Basic*) into `WHATSAPP_APP_SECRET`, and invent a `WHATSAPP_VERIFY_TOKEN` (any text).
4. In *WhatsApp > Configuration > Webhook* click *Edit*: callback URL `https://<your API>/api/v1/webhooks/whatsapp`, verify token = your
   `WHATSAPP_VERIFY_TOKEN`. Then *subscribe* to the `messages` field. The server checks Meta's signature on every call.
5. A business can only START a chat with a template Meta has approved. In the app's *Templates* page write your message, click
   *Preview* to see the text in Meta's form (`{{1}}`, `{{2}}`), create the same template in Meta's WhatsApp Manager, and when Meta
   approves it set its status to *approved* in CustomerIQ. (Replies inside 24 hours of the customer's message need no template.)
6. In *Auto Messenger > Settings* turn **Dry run** off. (If `MESSAGING_DRY_RUN=true` is set on the server it stays on.)

**Email** uses the same mail setup as the sign-in codes (see step 4 above); nothing more to add.

**Shopify** (optional). In Shopify *Settings > Notifications > Webhooks* add webhooks (format JSON) for `orders/create`,
`fulfillments/create`, `fulfillments/update` and `products/create`, all pointing to `https://<your API>/api/v1/webhooks/shopify`.
Copy the signing secret shown at the bottom of that page into `SHOPIFY_WEBHOOK_SECRET` (and your shop address into `SHOPIFY_SHOP_DOMAIN`).
A customer's marketing tick-box at checkout counts as **email** consent only; WhatsApp consent is never assumed.

**Scheduler** (runs messages that were waiting, review requests, campaign batches and journeys). The site has no background
workers, so GitHub knocks on the API every hour. In the API project add `SCHEDULER_SECRET` (a long random text). In the GitHub
repository open *Settings > Secrets and variables > Actions* and add `SCHEDULER_URL` (the API address) and the same `SCHEDULER_SECRET`.
The timetable is `.github/workflows/scheduler.yml`; the *Run workflow* button tries it by hand. (If GitHub refuses to accept a push
that changes a workflow file, add that file on github.com instead.)

**Customer videos** are kept in a second private bucket named `customer-media` in Supabase Storage (create it the same way as
`competitor-ads`, *Public bucket* off). `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are the ones from the screenshots step.

## Batch 1 additions (migrations 0022 to 0025)

No new environment variables. Run `scripts/migrate_remote.py` once to apply them (it applies every pending migration).

- **Model Report Card** (`/models`): each model's score next to its baseline and the Shown/Hidden decision. A history line is saved only when a decision or score changes (table `model_reports`).
- **Churn "Why?"**: three reasons on each customer's page, measured by asking the model again with one input set to a typical value.
- **Inventory** (`/inventory`): stock items with a SKU; a confirmed order reserves stock, a dispatched order sells it. Orders find items by SKU or name (`Name x2` means two units). Release a cancelled order's reservation, or restock a returned order, with `POST /api/v1/inventory/orders/{id}/release` and `/restock`.
- **COD confirmation** (`/messenger/cod`): approve the `cod_confirmation` template (Templates, "Add unboxing and review templates"). The customer replies YES or NO (or taps a Confirm / Cancel quick-reply button on the Meta template). No answer in 12 hours: "needs a phone call" and the order shows one Order Risk level higher.
- **Customer records**: notes, tags and source on each customer's page, a timeline, `/duplicates` to merge customers with the same email, and erase (anonymise keeps the orders as anonymous figures; delete removes them).

## Workflows (migration 0026)

Run `scripts/migrate_remote.py` to add the workflow tables. Workflows are built at **Workflows** and read at **Workflow Logs**.

- Triggers that fire today: a new customer, a new order, an order status change, stock falling to its warning level, a customer's WhatsApp message, a customer silent for N days, every day, every Monday.
- Actions: send a WhatsApp or email message (through the same consent, quiet-hours and weekly-limit checks as everything else), add or remove a tag, make a to-do, show a notification, change an order's status (forward only), call an approved web address.
- Waiting steps and retries are kept in the `jobs` table. The hourly scheduler (see the Auto Messenger section) runs them, so the GitHub Actions schedule must be set up for waits to work. The "Run waiting steps now" button does the same by hand.
- `WORKFLOW_WEBHOOK_URLS` (optional): comma separated https addresses a workflow may call. Empty means the web-address action is refused.

## Troubleshooting

| You see | Likely cause and fix |
| --- | --- |
| `/api/v1/health` says `"database":"unavailable"` | A `DB_*` value is wrong (host must contain `pooler.supabase.com`), the tables were not created (step 2), or the Supabase project is paused. |
| Vercel build of the API fails on install | Check the build log; the project needs Python 3.13 (set by `backend/.python-version`). Tell me the last lines of the log. |
| The site says **"We couldn't reach the server"** | `NEXT_PUBLIC_API_BASE_URL` is missing or wrong (then redeploy the website), or the API address answers with a Vercel sign-in page (see step 3). |
| Sign-in works, then you are sent back to sign in | The API is not in production mode, or the website address is not exactly `FRONTEND_ORIGINS`. |
| *"This request came from a website that is not allowed"* | `FRONTEND_ORIGINS` does not match the address in the browser bar. Fix it and redeploy the API. |
| No email arrives, or the page says "We couldn't send the email" | Check the spam folder first. The message now ends with the reason: `[OSError, error 99]` means this host cannot reach SMTP servers (use the mail relay); "unexpected way" means the script is not deployed with access **Anyone** or the address does not end in `/exec`; "refused the login" means `MAIL_WEBHOOK_SECRET` differs from the one in the script. Fix it and redeploy the API. |
| "Create an account" does not appear | Sign-up needs the email variables (`MAIL_WEBHOOK_URL` + `MAIL_WEBHOOK_SECRET`, or `BREVO_API_KEY` + `MAIL_FROM`, or `SMTP_*`), and `ALLOW_SIGNUP` must not be `false`. The owner account must already exist and be confirmed. |
| **"That setup code is not correct"** | Use the value of `SETUP_CODE` from the API project's settings. |
| A screenshot cannot be saved ("Screenshot storage is not set up") | `SUPABASE_URL` or `SUPABASE_SERVICE_KEY` is missing in the API project, or the bucket `competitor-ads` does not exist. |
| Meta says *The callback URL or verify token couldn't be validated* | `WHATSAPP_VERIFY_TOKEN` on Vercel differs from the one typed in Meta, or the API was not redeployed after you added it. |
| Messages stay *skipped: no_consent* | The customer has no recorded consent. Record it in *Auto Messenger > Consent* (only if they really agreed). |
| Messages are *skipped: meta_template_not_approved* | Business-started WhatsApp messages need a template approved by Meta. Set its status to *approved* in *Templates* after Meta approves it. |
| Nothing happens overnight | Quiet hours (default 21:00 to 10:00 Pakistan time): messages wait in the queue. The scheduler sends them in the morning. |
| The GitHub *Auto Messenger scheduler* run fails with HTTP 403 | `SCHEDULER_SECRET` in GitHub differs from the one on Vercel. HTTP 503 means it is not set on Vercel. |
| CSV upload fails on the live site only | The file is over 4.5 MB (see "Free limits"). |
| The assistant says **no remaining credits** | Add API credits in the Claude Console (a Claude Pro subscription does not include them). |

## Security checklist before real customer data

- [ ] The GitHub repository is **private**.
- [ ] `APP_ENV=production` and a `SETUP_CODE` are set on the API project.
- [ ] You know that every confirmed account sees all imported data (see the note under "Email codes").
- [ ] You created the first account yourself and confirmed "Create your account" no longer appears.
- [ ] No keys or passwords are in the repository.
- [ ] You have the right to use your customers' data, and you are not on a plan that forbids business use (Vercel Hobby is non-commercial).
