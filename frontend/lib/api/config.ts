// API configuration for the FastAPI backend.
//
// Demo mode: NEXT_PUBLIC_API_BASE_URL is not set. Pages show clearly labelled
// sample data from `lib/mock`, and features that need the server are disabled.
// Live mode: the variable is set. Requests go to the backend, and failures are
// shown as errors — never silently replaced with sample data.
//
// Never put secrets (OpenAI keys, DB credentials) in NEXT_PUBLIC_ vars: they are
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
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(
      `Could not reach the API at ${API_BASE_URL}. Check that the backend is running.`,
      undefined,
      "network_error",
    );
  }

  if (!response.ok) {
    // The backend returns {"error": {code, message, details}}; fall back if not.
    const body = (await response.json().catch(() => null)) as ErrorBody | null;
    throw new ApiError(
      body?.error?.message ?? `Request failed with status ${response.status}.`,
      response.status,
      body?.error?.code,
      body?.error?.details,
    );
  }
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
