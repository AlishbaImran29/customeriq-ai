"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, CheckCircle2, Circle, Eye, EyeOff, Info, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { AuthProblem, MIN_PASSWORD_LENGTH, getMe, safeNext, signIn, signOut, signUp } from "@/lib/api/auth";
import { API_MODE } from "@/lib/api/config";
import { supabaseBrowser } from "@/lib/supabase/client";
import { SUPABASE_CONFIGURED } from "@/lib/supabase/env";
import { cn } from "@/lib/utils";

type Mode = "signin" | "signup";
type Field = "name" | "email" | "password" | "confirm";
type FormError = { message: string; field?: Field };
type View = { kind: "loading" } | { kind: "form" } | { kind: "pending"; email: string };

const NOTICES: Record<string, string> = {
  expired: "Your session ended, so please sign in again to continue.",
  signedout: "You've been signed out. See you next time!",
};

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const notice = NOTICES[params.get("reason") ?? ""];

  const [view, setView] = useState<View>({ kind: "loading" });
  const [mode, setMode] = useState<Mode>(params.get("mode") === "signup" ? "signup" : "signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Someone who is already signed in goes straight on (or sees the "waiting for approval" screen).
  useEffect(() => {
    if (API_MODE === "demo" || !SUPABASE_CONFIGURED) return;
    let cancelled = false;
    supabaseBrowser().auth.getSession().then(async ({ data }) => {
      if (cancelled) return;
      if (!data.session) return setView({ kind: "form" });
      try {
        const me = await getMe();
        if (cancelled) return;
        if (me.isActive) router.replace(next);
        else setView({ kind: "pending", email: me.email });
      } catch {
        if (!cancelled) setView({ kind: "form" });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [next, router]);

  if (API_MODE === "demo") {
    return (
      <Panel title="No sign-in needed">
        <p className="text-sm text-ink-2">
          This is demo mode: no backend is connected, so the app shows sample data and does not need an account.
        </p>
        <Link href="/" className="mt-4 inline-flex text-sm font-medium text-accent hover:text-accent">
          Go to the demo dashboard
        </Link>
      </Panel>
    );
  }

  if (!SUPABASE_CONFIGURED) {
    return (
      <Panel title="Sign-in is not set up">
        <p className="text-sm text-ink-2">
          Site owner: add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY to the website settings, then redeploy.
        </p>
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

  if (view.kind === "pending") {
    return (
      <Panel title="Waiting for approval" subtitle={`You are signed in as ${view.email}.`}>
        <p className="flex items-start gap-2 rounded-xl bg-info/10 px-3 py-2 text-sm text-info" role="status">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          The owner of this site has to approve your account before you can see any customer data. Ask them to open Team and approve you.
        </p>
        <Button
          variant="secondary"
          className="mt-4 h-11 w-full"
          onClick={async () => {
            await signOut();
            setView({ kind: "form" });
          }}
        >
          Sign out
        </Button>
      </Panel>
    );
  }

  const creating = mode === "signup";
  const fieldError = (field: Field) => (error?.field === field ? error.message : undefined);
  const generalError = error && !error.field ? error.message : null;

  function validate(): FormError | null {
    if (creating && !name.trim()) return { message: "Please enter your name.", field: "name" };
    if (!email.trim() || !email.includes("@")) return { message: "Please enter a valid email address.", field: "email" };
    if (!password) return { message: "Please enter your password.", field: "password" };
    if (creating && password.length < MIN_PASSWORD_LENGTH) return { message: `Choose a longer password (at least ${MIN_PASSWORD_LENGTH} characters).`, field: "password" };
    if (creating && password !== confirm) return { message: "The two passwords do not match.", field: "confirm" };
    return null;
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const problem = validate();
    if (problem) return setError(problem);
    setError(null);
    setSubmitting(true);
    try {
      if (creating) {
        const result = await signUp(name, email, password);
        if (!result.signedIn) {
          setMode("signin");
          setError({ message: "Account created. Sign in to continue. (If it asks you to confirm your email, the site owner has to switch email confirmation off in Supabase.)" });
          return;
        }
      } else {
        await signIn(email, password);
      }
      const me = await getMe();
      if (me.isActive) router.replace(next);
      else setView({ kind: "pending", email: me.email });
    } catch (cause) {
      setError(cause instanceof AuthProblem ? { message: cause.message, field: cause.field } : { message: "Something went wrong. Please try again." });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Panel title={creating ? "Create your account" : "Welcome back"} subtitle={creating ? "Use your email and a password. There is nothing to confirm." : "Sign in to see your customer data."}>
      {notice && !error ? (
        <p className="mb-4 flex items-start gap-2 rounded-xl bg-info/10 px-3 py-2 text-sm text-info" role="status">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {notice}
        </p>
      ) : null}

      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {creating ? (
          <FieldBox id="name" label="Your name" error={fieldError("name")}>
            <Input id="name" autoComplete="name" required value={name} onChange={(e) => setName(e.target.value)} aria-invalid={fieldError("name") ? true : undefined} className={cn("h-11", fieldError("name") && "border-danger")} />
          </FieldBox>
        ) : null}

        <FieldBox id="email" label="Email" error={fieldError("email")}>
          <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} aria-invalid={fieldError("email") ? true : undefined} className={cn("h-11", fieldError("email") && "border-danger")} />
        </FieldBox>

        <FieldBox id="password" label="Password" error={fieldError("password")} hint={creating ? <PasswordHint password={password} /> : undefined}>
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
              className={cn("h-11 pr-11", fieldError("password") && "border-danger")}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              aria-pressed={showPassword}
              className="absolute right-1 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-lg text-muted hover:bg-surface-3 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
            >
              {showPassword ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
            </button>
          </div>
        </FieldBox>

        {creating ? (
          <FieldBox id="confirm" label="Confirm password" error={fieldError("confirm")}>
            <Input id="confirm" type={showPassword ? "text" : "password"} autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} aria-invalid={fieldError("confirm") ? true : undefined} className={cn("h-11", fieldError("confirm") && "border-danger")} />
          </FieldBox>
        ) : null}

        {generalError ? (
          <p role="alert" className="flex items-start gap-2 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            {generalError}
          </p>
        ) : null}

        <Button type="submit" disabled={submitting} className="h-11 w-full text-base">
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
          {submitting ? (creating ? "Creating your account…" : "Signing in…") : creating ? "Create account" : "Sign in"}
        </Button>
      </form>

      <p className="mt-5 text-center text-sm text-ink-2">
        {creating ? "Already have an account?" : "New here?"}{" "}
        <button
          type="button"
          onClick={() => {
            setMode(creating ? "signin" : "signup");
            setError(null);
          }}
          className="font-medium text-accent hover:text-accent"
        >
          {creating ? "Sign in" : "Create an account"}
        </button>
      </p>
      {creating ? <p className="mt-2 text-center text-xs text-faint">The first account on a new site becomes the owner. Later accounts wait for the owner&apos;s approval.</p> : null}
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
    <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-6 shadow-sm sm:p-8">
      <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
      {subtitle ? <p className="mt-1 mb-6 text-sm text-muted">{subtitle}</p> : <div className="mb-6" />}
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
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink">
        {label}
        {optional ? <span className="ml-1 font-normal text-faint">(optional)</span> : null}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="mt-1.5 flex items-start gap-1.5 text-sm text-danger">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {error}
        </p>
      ) : hint ? (
        <div className="mt-1.5 text-xs text-muted">{hint}</div>
      ) : null}
    </div>
  );
}

function PasswordHint({ password }: { password: string }) {
  const long = password.length >= MIN_PASSWORD_LENGTH;
  return (
    <span className={cn("inline-flex items-center gap-1 font-medium", long ? "text-success" : "text-muted")}>
      {long ? <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> : <Circle className="h-3.5 w-3.5" aria-hidden="true" />}
      At least {MIN_PASSWORD_LENGTH} characters
    </span>
  );
}
