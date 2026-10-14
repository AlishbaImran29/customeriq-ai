// API configuration for the future FastAPI backend.
//
// No backend is connected yet: every service in `lib/api` currently resolves
// with mock data from `lib/mock`. When the backend is ready, set
// NEXT_PUBLIC_API_BASE_URL and replace the mock return values with `apiGet`
// calls. Never put secrets (OpenAI keys, DB credentials) in NEXT_PUBLIC_ vars —
// AI calls must be proxied through the backend.

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

/** Where the data shown in the UI currently comes from. */
export const DATA_SOURCE: "mock" | "api" = "mock";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Typed JSON GET helper for when the backend is connected. */
export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE_URL) {
    throw new ApiError("API base URL is not configured.");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...init?.headers },
  });
  if (!response.ok) {
    throw new ApiError(`Request to ${path} failed`, response.status);
  }
  return (await response.json()) as T;
}