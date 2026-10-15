"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, Loader2, LogOut, UserRound } from "lucide-react";
import { getMe, initialsOf, signOut, type AuthUser } from "@/lib/api/auth";
import { API_MODE } from "@/lib/api/config";
import { cn } from "@/lib/utils";

/** Header avatar: the signed-in person (live mode) or a demo placeholder (demo mode). */
export function AccountMenu() {
  if (API_MODE === "demo") return <DemoAvatar />;
  return <SignedInMenu />;
}

// Placeholder only: demo mode has no sign-in, so no real user is shown.
function DemoAvatar() {
  return (
    <div className="flex items-center gap-2" title="Demo workspace. Sign-in is not available in demo mode.">
      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-200 text-slate-500" aria-hidden="true">
        <UserRound className="h-4 w-4" />
      </span>
      <span className="hidden text-xs leading-tight text-slate-500 md:block">
        <span className="block font-medium text-slate-700">Demo workspace</span>
        Sign-in not available
      </span>
      <span className="sr-only md:hidden">Demo workspace. Sign-in is not available in demo mode.</span>
    </div>
  );
}

function SignedInMenu() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    // A 401 here sends the browser to the sign-in page (see lib/api/config.ts).
    getMe()
      .then((me) => !cancelled && setUser(me))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent) {
        if (event.key === "Escape") setOpen(false);
      } else if (root.current && !root.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await signOut();
    } finally {
      router.replace("/login?reason=signedout");
      router.refresh();
    }
  }

  if (!user) {
    return <span className="h-8 w-8 animate-pulse rounded-full bg-slate-200" role="status" aria-label="Loading your account" />;
  }

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`Account menu for ${user.name}`}
        className="flex items-center gap-2 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-teal-600 text-xs font-semibold text-white" aria-hidden="true">
          {initialsOf(user)}
        </span>
        <span className="hidden max-w-[10rem] truncate text-sm font-medium text-slate-700 md:block">{user.name}</span>
      </button>

      <div
        role="menu"
        className={cn(
          "absolute right-0 z-30 mt-2 w-64 rounded-2xl border border-slate-200 bg-white p-1.5 shadow-lg",
          open ? "block" : "hidden",
        )}
      >
        <div className="px-3 py-2">
          <p className="truncate text-sm font-semibold text-slate-900">{user.name}</p>
          <p className="truncate text-xs text-slate-500">{user.email}</p>
        </div>
        <div className="my-1 border-t border-slate-100" />
        <Link
          href="/account"
          role="menuitem"
          onClick={() => setOpen(false)}
          className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40"
        >
          <KeyRound className="h-4 w-4" aria-hidden="true" /> Account &amp; password
        </Link>
        <button
          type="button"
          role="menuitem"
          onClick={handleSignOut}
          disabled={signingOut}
          className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40 disabled:opacity-60"
        >
          {signingOut ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <LogOut className="h-4 w-4" aria-hidden="true" />}
          {signingOut ? "Signing out…" : "Sign out"}
        </button>
      </div>
    </div>
  );
}
