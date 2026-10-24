// API configuration for the FastAPI backend.
//
// Demo mode: NEXT_PUBLIC_API_BASE_URL is not set. Pages show clearly labelled
// sample data from `lib/mock`, there is no sign-in, and features that need the
// server are disabled.
// Live mode: the variable is set to the backend's address. Pages require sign-in
// and failures are shown as errors — never silently replaced with sample data.
//
// Who calls what: Server Components call the backend directly (and forward the
// visitor's sign-in cookie). Browser code calls the site's own `/api/v1/...`
// path, which Next.js forwards to the backend (see `rewrites` in next.config.ts).
// That keeps the sign-in cookie first-party, so it works on any deployment.
//
// Never put secrets (AI provider keys, DB credentials) in NEXT_PUBLIC_ vars: they are
// bundled into the browser. AI calls must be proxied through the backend.

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/+$/, "");

export type ApiMode = "demo" | "live";

/** "live" when a backend URL is configured, otherwise "demo". */
export const API_MODE: ApiMode = API_BASE_URL ? "live" : "demo";

/**
 * Where the dashboard analytics come from: the API in live mode, sample data
 * from `lib/mock` in demo mode.
 */
export const DATA_SOURCE: "mock" | "api" = API_MODE === "live" ? "api" : "mock";

/** Error raised for failed API calls, carrying the backend's error code. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly code?: string,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ErrorBody = { error?: { code?: string; message?: string; details?: unknown } };

const inBrowser = () => typeof window !== "undefined";

/** Server: the backend itself. Browser: this site (forwarded to the backend). */
const requestBase = () => (inBrowser() ? "" : API_BASE_URL);

/** Browser only: when the session has ended, go to the sign-in page and come back after. */
function sendToSignIn() {
  if (window.location.pathname.startsWith("/login")) return;
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  // A full page load on purpose: it clears everything the old session had on screen,
  // and this helper runs outside React, where there is no router to use.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.href = `/login?reason=expired&next=${next}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE_URL) {
    throw new ApiError(
      "The API is not configured. Set NEXT_PUBLIC_API_BASE_URL to connect a backend.",
      undefined,
      "api_not_configured",
    );
  }

  let response: Response;
  try {
    response = await fetch(`${requestBase()}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(
      "We couldn't reach the server. Check your internet connection, or that the backend is running, and try again.",
      undefined,
      "network_error",
    );
  }

  if (!response.ok) {
    // The backend returns {"error": {code, message, details}}; fall back if not.
    const body = (await response.json().catch(() => null)) as ErrorBody | null;
    if (response.status === 401 && body?.error?.code === "not_signed_in" && inBrowser()) {
      sendToSignIn();
    }
    throw new ApiError(
      body?.error?.message ?? `Request failed with status ${response.status}.`,
      response.status,
      body?.error?.code,
      body?.error?.details,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Typed JSON GET. */
export function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  return request<T>(path, init);
}

/** POST multipart form data (file uploads). The browser sets the boundary header. */
export function apiPostForm<T>(path: string, form: FormData, init?: RequestInit): Promise<T> {
  return request<T>(path, { ...init, method: "POST", body: form });
}

/** DELETE, and parse the JSON response. */
export function apiDelete<T>(path: string, init?: RequestInit): Promise<T> {
  return request<T>(path, { ...init, method: "DELETE" });
}

/** POST a JSON body and parse the JSON response (undefined for 204 No Content). */
export function apiPostJson<T>(path: string, body: unknown, init?: RequestInit): Promise<T> {
  return request<T>(path, {
    ...init,
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
}

/** PATCH a JSON body and parse the JSON response. */
export function apiPatchJson<T>(path: string, body: unknown, init?: RequestInit): Promise<T> {
  return request<T>(path, {
    ...init,
    method: "PATCH",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
}

/** PUT a JSON body and parse the JSON response. */
export function apiPutJson<T>(path: string, body: unknown, init?: RequestInit): Promise<T> {
  return request<T>(path, {
    ...init,
    method: "PUT",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
}
