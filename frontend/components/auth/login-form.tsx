"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, CheckCircle2, Circle, Eye, EyeOff, Info, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { createAccount, getAuthStatus, safeNext, signIn, type AuthStatus } from "@/lib/api/auth";
import { API_MODE, ApiError } from "@/lib/api/config";
import { cn } from "@/lib/utils";

type View =
  | { kind: "loading" }
  | { kind: "unreachable"; message: string }
  | { kind: "ready"; status: AuthStatus };

type Field = "name" | "email" | "password" | "confirm" | "setupCode";
type FormError = { message: string; field?: Field };

const MIN_PASSWORD_LENGTH = 10;
const NOTICES: Record<string, string> = {
  expired: "Your session ended, so please sign in again to continue.",
  signedout: "You've been signed out. See you next time!",
};
const SERVER_FIELDS: Record<string, Field> = {
  email: "email",
  password: "password",
  name: "name",
  setupCode: "setupCode",
};

function describe(error: unknown): FormError {
  if (error instanceof ApiError) {
    const field = (error.details as { field?: string } | null)?.field;
    return { message: error.message, field: field ? SERVER_FIELDS[field] : undefined };
  }
  return { message: "Something went wrong. Please try again." };
}

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const notice = NOTICES[params.get("reason") ?? ""];

  const [view, setView] = useState<View>({ kind: "loading" });
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [setupCode, setSetupCode] = useState("");
  const [remember, setRemember] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (API_MODE === "demo") return;
    let cancelled = false;
    getAuthStatus()
      .then((status) => {
        if (cancelled) return;
        if (status.authenticated) router.replace(next);
        else setView({ kind: "ready", status });
      })
      .catch((cause: unknown) => {
        if (!cancelled) setView({ kind: "unreachable", message: describe(cause).message });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt, next, router]);

  if (API_MODE === "demo") {
    return (
      <Panel title="No sign-in needed">
        <p className="text-sm text-slate-600">
          This is demo mode: no backend is connected, so the app shows sample data and does not need an account.
        </p>
        <Link href="/" className="mt-4 inline-flex text-sm font-medium text-teal-700 hover:text-teal-800">
          Go to the demo dashboard
        </Link>
      </Panel>
    );
  }

  if (view.kind === "loading") {
    return (
      <Panel title="One moment…">
        <div className="space-y-4" role="status">
          <span className="sr-only">Loading…</span>
          <Skeleton className="h-11" />
          <Skeleton className="h-11" />
          <Skeleton className="h-11" />
        </div>
      </Panel>
    );
  }

  if (view.kind === "unreachable") {
    return (
      <Panel title="We can't reach the server">
        <p className="text-sm text-slate-600">{view.message}</p>
        <Button
          className="mt-4"
          variant="secondary"
          onClick={() => {
            setView({ kind: "loading" });
            setAttempt((n) => n + 1);
          }}
        >
          Try again
        </Button>
      </Panel>
    );
  }

  const { setupRequired, setupCodeRequired } = view.status;

  function validate(): FormError | null {
    const trimmed = email.trim();
    if (!trimmed || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(trimmed)) {
      return { message: "Please enter your email address, for example name@company.com.", field: "email" };
    }
    if (!password) return { message: "Please enter your password.", field: "password" };
    if (setupRequired) {
      if (password.length < MIN_PASSWORD_LENGTH) {
        return { message: `Your password needs at least ${MIN_PASSWORD_LENGTH} characters.`, field: "password" };
      }
      if (password !== confirm) return { message: "The two passwords don't match yet.", field: "confirm" };
      if (setupCodeRequired && !setupCode.trim()) {
        return { message: "Please enter the setup code from the person who set up this site.", field: "setupCode" };
      }
    }
    return null;
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (submitting) return;
    const problem = validate();
    setError(problem);
    if (problem) return;
    setSubmitting(true);
    try {
      if (setupRequired) {
        await createAccount({ name: name.trim(), email, password, setupCode: setupCode.trim() || undefined });
      } else {
        await signIn(email, password, remember);
      }
      // Keep the button busy while the next page loads, so it cannot be double-submitted.
      router.replace(next);
      router.refresh();
    } catch (cause) {
      setError(describe(cause));
      setSubmitting(false);
    }
  }

  const fieldError = (field: Field) => (error?.field === field ? error.message : undefined);
  const generalError = error && !error.field ? error.message : undefined;

  return (
    <Panel
      title={setupRequired ? "Create your account" : "Welcome back"}
      subtitle={
        setupRequired
          ? "You're the first one here. Set up the account that will own this workspace."
          : "Sign in to see your customer insights."
      }
    >
      {notice && !setupRequired ? (
        <p className="mb-4 flex items-start gap-2 rounded-xl bg-sky-50 px-3 py-2 text-sm text-sky-900" role="status">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {notice}
        </p>
      ) : null}

      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {setupRequired ? (
          <FieldBox id="name" label="Your name" optional error={fieldError("name")}>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
              placeholder="Alishba"
              maxLength={100}
              className="h-11"
            />
          </FieldBox>
        ) : null}

        <FieldBox id="email" label="Email" error={fieldError("email")}>
          <Input
            id="email"
            type="email"
            inputMode="email"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            autoFocus
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@company.com"
            aria-invalid={fieldError("email") ? true : undefined}
            aria-describedby={fieldError("email") ? "email-error" : undefined}
            className={cn("h-11", fieldError("email") && "border-rose-400")}
          />
        </FieldBox>

        <FieldBox
          id="password"
          label="Password"
          error={fieldError("password")}
          hint={setupRequired ? <PasswordHint password={password} /> : undefined}
        >
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete={setupRequired ? "new-password" : "current-password"}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={fieldError("password") ? true : undefined}
              aria-describedby={fieldError("password") ? "password-error" : undefined}
              className={cn("h-11 pr-11", fieldError("password") && "border-rose-400")}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              aria-pressed={showPassword}
              className="absolute right-1 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40"
            >
              {showPassword ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
            </button>
          </div>
        </FieldBox>

        {setupRequired ? (
          <FieldBox id="confirm" label="Confirm password" error={fieldError("confirm")}>
            <Input
              id="confirm"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              aria-invalid={fieldError("confirm") ? true : undefined}
              aria-describedby={fieldError("confirm") ? "confirm-error" : undefined}
              className={cn("h-11", fieldError("confirm") && "border-rose-400")}
            />
          </FieldBox>
        ) : null}

        {setupRequired && setupCodeRequired ? (
          <FieldBox
            id="setupCode"
            label="Setup code"
            error={fieldError("setupCode")}
            hint="This public site only lets someone with the setup code create the first account."
          >
            <Input
              id="setupCode"
              value={setupCode}
              onChange={(e) => setSetupCode(e.target.value)}
              autoComplete="off"
              spellCheck={false}
              className="h-11"
            />
          </FieldBox>
        ) : null}

        <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            className="h-4 w-4 rounded border-slate-300 accent-teal-600"
          />
          Keep me signed in on this device
        </label>

        {generalError ? (
          <p
            role="alert"
            className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            {generalError}
          </p>
        ) : null}

        <Button type="submit" disabled={submitting} className="h-11 w-full text-base">
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
          {submitting ? (setupRequired ? "Creating your account…" : "Signing in…") : setupRequired ? "Create account" : "Sign in"}
        </Button>
      </form>

      {!setupRequired ? (
        <details className="mt-5 text-sm text-slate-600">
          <summary className="cursor-pointer font-medium text-teal-700 hover:text-teal-800">
            Forgot your password?
          </summary>
          <p className="mt-2">
            Ask the person who set up this site to reset it for you. They can do it in a minute with the
            reset command described in the project README (<code>manage_users.py reset-password</code>).
          </p>
        </details>
      ) : null}
    </Panel>
  );
}

function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
      {subtitle ? <p className="mt-1 mb-6 text-sm text-slate-500">{subtitle}</p> : <div className="mb-6" />}
      {children}
    </div>
  );
}

function FieldBox({
  id,
  label,
  optional,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  optional?: boolean;
  error?: string;
  hint?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-slate-800">
        {label}
        {optional ? <span className="ml-1 font-normal text-slate-400">(optional)</span> : null}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="mt-1.5 flex items-start gap-1.5 text-sm text-rose-700">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {error}
        </p>
      ) : hint ? (
        <div className="mt-1.5 text-xs text-slate-500">{hint}</div>
      ) : null}
    </div>
  );
}

function PasswordHint({ password }: { password: string }) {
  const long = password.length >= MIN_PASSWORD_LENGTH;
  return (
    <>
      <span className={cn("inline-flex items-center gap-1 font-medium", long ? "text-emerald-700" : "text-slate-500")}>
        {long ? <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> : <Circle className="h-3.5 w-3.5" aria-hidden="true" />}
        At least {MIN_PASSWORD_LENGTH} characters
      </span>
      <span className="block">
        A few unrelated words work well and are easy to remember, like &ldquo;blue tractor sings loudly&rdquo;.
      </span>
    </>
  );
}
