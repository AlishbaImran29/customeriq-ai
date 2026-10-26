// Sign-in (browser side). Accounts and passwords are Supabase Auth (email + password, no email-confirmation step).
// The Supabase client keeps the sign-in in cookies; `lib/api/config.ts` sends its token to the API with every call.

import { apiGet } from "@/lib/api/config";
import { supabaseBrowser } from "@/lib/supabase/client";

export type AuthUser = {
  id: string;
  email: string;
  name: string;
  lastLoginAt: string | null;
  /** owner can do everything, staff the daily work, viewer can only look. The server enforces it. */
  role: "owner" | "staff" | "viewer";
  /** False while the owner has not approved the account yet: it cannot see any data until then. */
  isActive: boolean;
};

export const MIN_PASSWORD_LENGTH = 8;

/** A sign-in problem in words a person can act on. */
export class AuthProblem extends Error {
  constructor(message: string, readonly field?: "email" | "password" | "name") {
    super(message);
    this.name = "AuthProblem";
  }
}

function problemFrom(message: string): AuthProblem {
  const m = message.toLowerCase();
  if (m.includes("invalid login") || m.includes("invalid credentials")) return new AuthProblem("That email or password is not correct.");
  if (m.includes("already registered") || m.includes("already been registered")) return new AuthProblem("An account with this email already exists. Please sign in instead.", "email");
  if (m.includes("password") && (m.includes("least") || m.includes("weak") || m.includes("short"))) return new AuthProblem(`Choose a longer password (at least ${MIN_PASSWORD_LENGTH} characters).`, "password");
  if (m.includes("valid email") || m.includes("invalid email")) return new AuthProblem("Please enter a valid email address.", "email");
  if (m.includes("rate limit") || m.includes("too many")) return new AuthProblem("Too many attempts. Please wait a few minutes and try again.");
  if (m.includes("email not confirmed")) return new AuthProblem("This account's email is not confirmed. Ask the site owner to switch off email confirmation in Supabase (Authentication, Providers, Email).");
  if (m.includes("signup") && m.includes("disabled")) return new AuthProblem("Sign-ups are switched off in Supabase (Authentication, Sign In / Providers: turn on Allow new users to sign up, and Email).");
  if (m.includes("api key") || m.includes("apikey") || m.includes("jwt")) return new AuthProblem("The Supabase key on the website is not correct. Check NEXT_PUBLIC_SUPABASE_ANON_KEY in Vercel and redeploy.");
  if (m.includes("failed to fetch") || m.includes("network")) return new AuthProblem("Could not reach Supabase. Check NEXT_PUBLIC_SUPABASE_URL in Vercel and redeploy.");
  return new AuthProblem(`Something went wrong (${message.slice(0, 120)}). Please try again.`);
}

export const getMe = () => apiGet<AuthUser>("/api/v1/auth/me");

export async function signIn(email: string, password: string): Promise<void> {
  const { error } = await supabaseBrowser().auth.signInWithPassword({ email: email.trim(), password });
  if (error) throw problemFrom(error.message);
}

/** Creates the account. With email confirmation switched off in Supabase the person is signed in at once. */
export async function signUp(name: string, email: string, password: string): Promise<{ signedIn: boolean }> {
  const { data, error } = await supabaseBrowser().auth.signUp({ email: email.trim(), password, options: { data: { name: name.trim() } } });
  if (error) throw problemFrom(error.message);
  return { signedIn: Boolean(data.session) };
}

export async function signOut(): Promise<void> {
  await supabaseBrowser().auth.signOut();
}

/** Checks the current password by signing in with it, then sets the new one. */
export async function changePassword(email: string, currentPassword: string, newPassword: string): Promise<void> {
  const supabase = supabaseBrowser();
  const check = await supabase.auth.signInWithPassword({ email, password: currentPassword });
  if (check.error) throw new AuthProblem("Your current password is not correct.", "password");
  const { error } = await supabase.auth.updateUser({ password: newPassword });
  if (error) throw problemFrom(error.message);
}

/** Only follow same-site paths after sign-in (never an address on another website). */
export function safeNext(next: string | null | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login") ? next : "/";
}

export function initialsOf(user: Pick<AuthUser, "name" | "email">): string {
  const source = user.name.trim() || user.email;
  const parts = source.split(/[\s@._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "?") + (parts.length > 1 ? (parts[1]?.[0] ?? "") : "")).toUpperCase();
}
