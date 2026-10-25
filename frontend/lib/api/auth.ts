// Sign-in service. Runs in the browser (cookies are HttpOnly, so page code never sees them).

import { apiGet, apiPostJson } from "@/lib/api/config";

export type AuthUser = {
  id: string;
  email: string;
  name: string;
  lastLoginAt: string | null;
  /** owner can do everything, staff the daily work, viewer can only look. The server enforces it. */
  role?: "owner" | "staff" | "viewer";
};

/** What the sign-in page needs to know before anyone is signed in. */
export type AuthStatus = {
  /** No account exists yet: show "create your account". */
  setupRequired: boolean;
  /** Creating the first account needs the owner's setup code. */
  setupCodeRequired: boolean;
  authenticated: boolean;
  user: AuthUser | null;
  /** Anyone with a real email address may create an account. */
  signupOpen: boolean;
  /** New accounts confirm their email with a 6-digit code. */
  verificationEnabled: boolean;
};

/** The account exists, but the email still has to be confirmed with the code we sent. */
export type VerificationPending = { verificationRequired: true; email: string };

export const needsVerification = (result: AuthUser | VerificationPending): result is VerificationPending =>
  "verificationRequired" in result;

export const getAuthStatus = () => apiGet<AuthStatus>("/api/v1/auth/status");

export const getMe = () => apiGet<AuthUser>("/api/v1/auth/me");

export const signIn = (email: string, password: string, remember: boolean) =>
  apiPostJson<AuthUser>("/api/v1/auth/login", { email, password, remember });

export const createAccount = (input: {
  name: string;
  email: string;
  password: string;
  setupCode?: string;
}) => apiPostJson<AuthUser | VerificationPending>("/api/v1/auth/setup", { ...input, remember: true });

export const signUp = (input: { name: string; email: string; password: string }) =>
  apiPostJson<VerificationPending>("/api/v1/auth/signup", input);

export const verifyEmail = (email: string, code: string, remember: boolean) =>
  apiPostJson<AuthUser>("/api/v1/auth/verify", { email, code, remember });

export const resendCode = (email: string) => apiPostJson<VerificationPending>("/api/v1/auth/resend", { email });

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
