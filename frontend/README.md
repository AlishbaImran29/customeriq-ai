# CustomerIQ AI — Frontend

Next.js 16 (App Router) dashboard for CustomerIQ AI. For full setup and run
instructions, see the [project README](../README.md).

## Run

```powershell
npm.cmd install      # first time only (Bash: npm install)
npm.cmd run dev      # Bash: npm run dev
```

## Demo vs live data

| `NEXT_PUBLIC_API_BASE_URL` (in `.env.local`) | Mode | Data shown |
| --- | --- | --- |
| not set | Demo | Sample data from `lib/mock`, labelled "Demo data" |
| `http://127.0.0.1:8000` | Live | Your imported data from the FastAPI backend, labelled "Live data" |

Copy `.env.example` to `.env.local` for live mode. Only public values belong in
these files: anything starting with `NEXT_PUBLIC_` is bundled into the browser,
so never put API keys or passwords here. A failed live request shows an error
state with **Try again**; it never falls back to sample data.

## Sign-in

In live mode `proxy.ts` sends visitors without a sign-in cookie to `/login` (it only
checks that the cookie exists; the backend decides if it is still valid, and an expired
session ends at `/login?reason=expired`). Demo mode has no sign-in. The browser only talks
to this site: `next.config.ts` forwards `/api/v1/*` to the backend, so the cookie is
first-party. Server Components forward the visitor's cookie when they call the backend.
`/api` is excluded from the proxy matcher so file uploads are not buffered by it.

## Where things are

| Path | Purpose |
| --- | --- |
| `app/<page>/page.tsx` | Pages. Each renders its header instantly and streams data inside `<Suspense>`. |
| `lib/api/config.ts` | API client (`apiGet`, `apiPostForm`, `apiPostJson`), `API_MODE`, `ApiError`. |
| `lib/api/customer-intelligence.ts` | Server-only data loaders for the dashboards (demo or live). |
| `lib/api/data-import.ts`, `lib/api/assistant.ts` | Import and assistant calls (run in the browser). |
| `lib/types.ts` | Shared types; `null` means "not available yet" (e.g. predictions). |
| `components/data-state.tsx` | Data banner, empty, error, and loading states shared by pages. |
| `lib/mock/` | Sample data for demo mode only. |

## Checks

```powershell
npx.cmd tsc --noEmit
npm.cmd run lint
npm.cmd run build
```

This project uses Next.js 16, which differs from older versions. See
`AGENTS.md` and the guides in `node_modules/next/dist/docs/` before changing
framework-level code.
