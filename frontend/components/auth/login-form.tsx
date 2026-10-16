"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, CheckCircle2, Circle, Eye, EyeOff, Info, Loader2, MailCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  createAccount,
  getAuthStatus,
  needsVerification,
  resendCode,
  safeNext,
  signIn,
  signUp,
  verifyEmail,
  type AuthStatus,
} from "@/lib/api/auth";
import { API_MODE, ApiError } from "@/lib/api/config";
import { cn } from "@/lib/utils";

type View =
  | { kind: "loading" }
  | { kind: "unreachable"; message: string }
  | { kind: "ready"; status: AuthStatus };

type Field = "name" | "email" | "password" | "confirm" | "setupCode" | "code";
type Mode = "signin" | "signup" | "verify";
type FormError = { message: string; field?: Field };

const MIN_PASSWORD_LENGTH = 10;
const CODE_LENGTH = 6;
const RESEND_SECONDS = 60;
const NOTICES: Record<string, string> = {
  expired: "Your session ended, so please sign in again to continue.",
  signedout: "You've been signed out. See you next time!",
};
const SERVER_FIELDS: Record<string, Field> = {
  email: "email",
  password: "password",
  name: "name",
  setupCode: "setupCode",
  code: "code",
};

// Why an email could not be sent (sent by the server as a short code), in words for the site owner.
const EMAIL_FAILURE_HINTS: Record<string, string> = {
  login_refused: "The email account refused the login. (Site owner: check SMTP_USER and the App Password.)",
  sender_refused: "The email account refused to send from this address. (Site owner: check SMTP_USER and SMTP_FROM.)",
  address_refused: "The email address was refused. Please check it for typing mistakes.",
  timeout: "The email service did not answer in time. Please try again.",
  disconnected: "The email service closed the connection. (Site owner: check SMTP_HOST and SMTP_PORT.)",
  host_not_found: "The email host name was not found. (Site owner: check SMTP_HOST, it should be smtp.gmail.com for Gmail.)",
  port_closed: "The email service refused the connection on that port. (Site owner: check SMTP_PORT, try 587 or 465.)",
  network_blocked: "This server has no network route to the email service. (Site owner: try SMTP_PORT=465 with SMTP_SECURITY=ssl.)",
  tls_failed: "The secure connection to the email service failed. (Site owner: 587 needs SMTP_SECURITY=starttls, 465 needs SMTP_SECURITY=ssl.)",
  unreachable: "The server could not reach the email service. (Site owner: check SMTP_HOST and SMTP_PORT.)",
  smtp_error: "The email service reported an error.",
};

function describe(error: unknown): FormError {
  if (error instanceof ApiError) {
    const details = error.details as { field?: string; reason?: string; kind?: string; errno?: number | null } | null;
    const hint = error.code === "email_send_failed" && details?.reason ? EMAIL_FAILURE_HINTS[details.reason] : undefined;
    const technical = hint && details?.kind ? ` [${details.kind}${details.errno ? `, error ${details.errno}` : ""}]` : "";
    return {
      message: hint ? `${error.message} ${hint}${technical}` : error.message,
      field: details?.field ? SERVER_FIELDS[details.field] : undefined,
    };
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
  const [mode, setMode] = useState<Mode>(params.get("mode") === "signup" ? "signup" : "signin");
  const [pendingEmail, setPendingEmail] = useState("");
  const [code, setCode] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((seconds) => seconds - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

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

  const { setupRequired, setupCodeRequired, signupOpen, verificationEnabled } = view.status;
  // "Creating" covers the owner's first account and ordinary sign-ups; sign-ins have fewer fields.
  const creating = setupRequired || (mode === "signup" && signupOpen);

  function startVerify(address: string) {
    setPendingEmail(address);
    setCode("");
    setError(null);
    setInfo(null);
    setCooldown(RESEND_SECONDS);
    setSubmitting(false);
    setMode("verify");
  }

  async function onVerify(event: React.FormEvent) {
    event.preventDefault();
    if (submitting) return;
    if (code.length !== CODE_LENGTH) {
      setError({ message: `Please enter the ${CODE_LENGTH}-digit code from the email.`, field: "code" });
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await verifyEmail(pendingEmail, code, remember);
      router.replace(next);
      router.refresh();
    } catch (cause) {
      setError(describe(cause));
      setSubmitting(false);
    }
  }

  async function onResend() {
    if (cooldown > 0) return;
    setError(null);
    setInfo(null);
    setCooldown(RESEND_SECONDS);
    try {
      await resendCode(pendingEmail);
      setInfo("If that address is waiting for confirmation, a new code is on its way.");
    } catch (cause) {
      setError(describe(cause));
    }
  }

  function validate(): FormError | null {
    const trimmed = email.trim();
    if (!trimmed || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(trimmed)) {
      return { message: "Please enter your email address, for example name@company.com.", field: "email" };
    }
    if (!password) return { message: "Please enter your password.", field: "password" };
    if (creating) {
      if (password.length < MIN_PASSWORD_LENGTH) {
        return { message: `Your password needs at least ${MIN_PASSWORD_LENGTH} characters.`, field: "password" };
      }
      if (password !== confirm) return { message: "The two passwords don't match yet.", field: "confirm" };
      if (setupRequired && setupCodeRequired && !setupCode.trim()) {
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
      const result = setupRequired
        ? await createAccount({ name: name.trim(), email, password, setupCode: setupCode.trim() || undefined })
        : creating
          ? await signUp({ name: name.trim(), email, password })
          : await signIn(email, password, remember);
      if (needsVerification(result)) {
        startVerify(result.email);
        return;
      }
      // Keep the button busy while the next page loads, so it cannot be double-submitted.
      router.replace(next);
      router.refresh();
    } catch (cause) {
      // Right password, but the email was never confirmed: we have just sent a new code.
      if (cause instanceof ApiError && cause.code === "email_not_verified") {
        startVerify((cause.details as { email?: string } | null)?.email ?? email.trim().toLowerCase());
        return;
      }
      setError(describe(cause));
      setSubmitting(false);
    }
  }

  const fieldError = (field: Field) => (error?.field === field ? error.message : undefined);
  const generalError = error && !error.field ? error.message : undefined;

  if (mode === "verify") {
    return (
      <Panel title="Check your email" subtitle={`We sent a ${CODE_LENGTH}-digit code to ${pendingEmail}.`}>
        <form onSubmit={onVerify} noValidate className="space-y-4">
          <FieldBox
            id="code"
            label="Verification code"
            error={fieldError("code")}
            hint="It can take a minute to arrive. Check your spam or junk folder too."
          >
            <Input
              id="code"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, CODE_LENGTH))}
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              placeholder="123456"
              maxLength={CODE_LENGTH}
              aria-invalid={fieldError("code") ? true : undefined}
              className={cn("h-12 text-center text-2xl tracking-[0.4em]", fieldError("code") && "border-rose-400")}
            />
          </FieldBox>

          {info ? (
            <p className="flex items-start gap-2 rounded-xl bg-sky-50 px-3 py-2 text-sm text-sky-900" role="status">
              <MailCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              {info}
            </p>
          ) : null}
          {generalError ? (
            <p role="alert" className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              {generalError}
            </p>
          ) : null}

          <Button type="submit" disabled={submitting} className="h-11 w-full text-base">
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
            {submitting ? "Checking…" : "Verify and continue"}
          </Button>
        </form>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-2 text-sm">
          <button
            type="button"
            onClick={onResend}
            disabled={cooldown > 0}
            className="font-medium text-teal-700 hover:text-teal-800 disabled:cursor-not-allowed disabled:text-slate-400"
          >
            {cooldown > 0 ? `Send a new code in ${cooldown}s` : "Send a new code"}
          </button>
          <button
            type="button"
            onClick={() => {
              setMode(setupRequired ? "signin" : "signup");
              setError(null);
              setInfo(null);
            }}
            className="text-slate-600 hover:text-slate-900"
          >
            Use a different email
          </button>
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      title={creating ? "Create your account" : "Welcome back"}
      subtitle={
        setupRequired
          ? "You're the first one here. Set up the account that will own this workspace."
          : creating
            ? "Use a real email address. We'll send you a code to confirm it."
            : "Sign in to see your customer insights."
      }
    >
      {notice && !creating ? (
        <p className="mb-4 flex items-start gap-2 rounded-xl bg-sky-50 px-3 py-2 text-sm text-sky-900" role="status">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {notice}
        </p>
      ) : null}

      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {creating ? (
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
          hint={creating ? <PasswordHint password={password} /> : undefined}
        >
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete={creating ? "new-password" : "current-password"}
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

        {creating ? (
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
          {submitting ? (creating ? "Creating your account…" : "Signing in…") : creating ? (verificationEnabled ? "Create account and send code" : "Create account") : "Sign in"}
        </Button>
      </form>

      {!setupRequired && signupOpen ? (
        <p className="mt-5 text-center text-sm text-slate-600">
          {creating ? "Already have an account?" : "New here?"}{" "}
          <button
            type="button"
            onClick={() => {
              setMode(creating ? "signin" : "signup");
              setError(null);
            }}
            className="font-medium text-teal-700 hover:text-teal-800"
          >
            {creating ? "Sign in" : "Create an account"}
          </button>
        </p>
      ) : null}

      {!creating ? (
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
