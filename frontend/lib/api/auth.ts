// Sign-in service. Runs in the browser (cookies are HttpOnly, so page code never sees them).

import { apiGet, apiPostJson } from "@/lib/api/config";

export type AuthUser = {
  id: string;
  email: string;
  name: string;
  lastLoginAt: string | null;
};

/** What the sign-in page needs to know before anyone is signed in. */
export type AuthStatus = {
  /** No account exists yet: show "create your account". */
  setupRequired: boolean;
  /** Creating the first account needs the owner's setup code. */
  setupCodeRequired: boolean;
  authenticated: boolean;
  user: AuthUser | null;
};

export const getAuthStatus = () => apiGet<AuthStatus>("/api/v1/auth/status");

export const getMe = () => apiGet<AuthUser>("/api/v1/auth/me");

export const signIn = (email: string, password: string, remember: boolean) =>
  apiPostJson<AuthUser>("/api/v1/auth/login", { email, password, remember });

export const createAccount = (input: {
  name: string;
  email: string;
  password: string;
  setupCode?: string;
}) => apiPostJson<AuthUser>("/api/v1/auth/setup", { ...input, remember: true });

export const signOut = () => apiPostJson<void>("/api/v1/auth/logout", {});

export const changePassword = (currentPassword: string, newPassword: string) =>
  apiPostJson<void>("/api/v1/auth/change-password", { currentPassword, newPassword });

/** Only follow same-site paths after sign-in (never an address on another website). */
export function safeNext(next: string | null | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login") ? next : "/";
}

export function initialsOf(user: Pick<AuthUser, "name" | "email">): string {
  const source = user.name.trim() || user.email;
  const parts = source.split(/[\s@._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "?") + (parts.length > 1 ? (parts[1]?.[0] ?? "") : "")).toUpperCase();
}
