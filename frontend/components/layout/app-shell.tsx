"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  Activity,
  Bot,
  HeartPulse,
  LayoutDashboard,
  Lightbulb,
  Menu,
  Sparkles,
  TrendingUp,
  Upload,
  Users,
  Wallet,
  X,
  Grid3x3,
} from "lucide-react";
import { AccountMenu } from "@/components/layout/account-menu";
import { CurrencyMenu } from "@/components/layout/currency-menu";
import { LanguageToggle } from "@/components/layout/language-toggle";
import { useLanguage } from "@/lib/i18n";
import { API_MODE } from "@/lib/api/config";
import { cn } from "@/lib/utils";

const LIVE = API_MODE === "live";

const navGroups = [
  {
    label: "Insights",
    items: [
      { href: "/", label: "Overview", icon: LayoutDashboard },
      { href: "/segmentation", label: "Segmentation", icon: Users },
      { href: "/churn", label: "Churn Prediction", icon: Activity },
      { href: "/cohorts", label: "Cohort Retention", icon: Grid3x3 },
      { href: "/clv", label: "Lifetime Value", icon: Wallet },
      { href: "/health", label: "Health Scores", icon: HeartPulse },
      { href: "/revenue", label: "Revenue Intelligence", icon: TrendingUp },
    ],
  },
  {
    label: "Actions",
    items: [
      { href: "/recommendations", label: "Recommendations", icon: Lightbulb },
      { href: "/assistant", label: "AI Business Assistant", icon: Bot },
    ],
  },
  {
    label: "Data",
    items: [{ href: "/import", label: "Import Data", icon: Upload }],
  },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

// Matches Tailwind's `lg` breakpoint, where the sidebar is always visible.
const DESKTOP_QUERY = "(min-width: 1024px)";

function subscribeDesktop(onChange: () => void) {
  const query = window.matchMedia(DESKTOP_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function useIsDesktop() {
  return useSyncExternalStore(
    subscribeDesktop,
    () => window.matchMedia(DESKTOP_QUERY).matches,
    () => true,
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const isDesktop = useIsDesktop();
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  // The off-canvas drawer is hidden from keyboard and screen readers while closed.
  const drawerHidden = !isDesktop && !open;

  function openDrawer() {
    setOpen(true);
    requestAnimationFrame(() => closeButtonRef.current?.focus());
  }

  /** Closes the drawer; returns focus to the menu button unless navigating away. */
  function closeDrawer(restoreFocus = true) {
    setOpen(false);
    if (restoreFocus) menuButtonRef.current?.focus();
  }

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const currentLabel =
    navGroups.flatMap((g) => g.items).find((item) => isActive(pathname, item.href))?.label ??
    "CustomerIQ AI";

  // The sign-in screen and landing page stand alone, without the sidebar and header.
  if (pathname.startsWith("/login") || pathname.startsWith("/welcome")) return <>{children}</>;

  return (
    <div className="min-h-full bg-slate-50 text-slate-900">
      <a
        href="#main-content"
        className="sr-only z-50 rounded-lg bg-white px-3 py-2 text-sm font-medium text-teal-800 shadow focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        {t("Skip to content")}
      </a>
      <div className="flex min-h-screen">
        {open ? (
          <div
            className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden"
            aria-hidden="true"
            onClick={() => closeDrawer()}
          />
        ) : null}
        <aside
          id="app-sidebar"
          inert={drawerHidden}
          className={cn(
            "fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-slate-800 bg-slate-950 text-slate-200 transition-transform duration-200 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0",
            open ? "translate-x-0" : "-translate-x-full",
          )}
        >
          <div className="flex items-center justify-between px-5 py-5">
            <Link href="/" className="flex items-center gap-2" onClick={() => closeDrawer(false)}>
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal-500 text-sm font-bold text-slate-950">
                IQ
              </span>
              <span>
                <span className="block text-sm font-semibold text-white">CustomerIQ AI</span>
                <span className="block text-[11px] text-slate-400">Predictive customer intelligence</span>
              </span>
            </Link>
            <button
              ref={closeButtonRef}
              type="button"
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-900 hover:text-white lg:hidden"
              onClick={() => closeDrawer()}
              aria-label="Close navigation"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <nav aria-label="Main" className="flex-1 space-y-5 overflow-y-auto px-3 pb-3">
            {navGroups.map((group) => (
              <div key={t(group.label)}>
                <p className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-slate-500">
                  {group.label}
                </p>
                <ul className="space-y-1">
                  {group.items.map((item) => {
                    const active = isActive(pathname, item.href);
                    return (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          onClick={() => closeDrawer(false)}
                          aria-current={active ? "page" : undefined}
                          className={cn(
                            "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/50",
                            active
                              ? "bg-teal-500/15 font-medium text-teal-200"
                              : "text-slate-400 hover:bg-slate-900 hover:text-white",
                          )}
                        >
                          <item.icon className="h-4 w-4" aria-hidden="true" />
                          {t(item.label)}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>
          <div className="m-3 rounded-xl border border-slate-800 bg-slate-900 p-3 text-xs text-slate-400">
            <p className="flex items-center gap-1 font-medium text-slate-200">
              <Sparkles className="h-3.5 w-3.5 text-teal-400" aria-hidden="true" />
              {t(LIVE ? "Live workspace" : "Demo workspace")}
            </p>
            <p className="mt-1">
              {t(LIVE ? "Dashboards use your imported data. Predictions appear only when a model passed its accuracy test." : "No backend configured. Dashboards show sample data.")}
            </p>
          </div>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur">
            <button
              ref={menuButtonRef}
              type="button"
              className="rounded-lg p-2 hover:bg-slate-100 lg:hidden"
              onClick={openDrawer}
              aria-label="Open navigation"
              aria-expanded={open}
              aria-controls="app-sidebar"
            >
              <Menu className="h-5 w-5" />
            </button>
            <p className="truncate text-sm font-medium text-slate-900 lg:hidden">{t(currentLabel)}</p>
            <p className="hidden text-sm text-slate-500 lg:block">
              {t("E-commerce growth copilot for Shopify, WooCommerce, and Magento")}
            </p>
            <div className="ml-auto flex items-center gap-3">
              <span
                className={cn(
                  "hidden rounded-full px-2.5 py-1 text-xs font-medium sm:inline",
                  LIVE ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800",
                )}
              >
                {t(LIVE ? "Live data" : "Demo data")}
              </span>
              <LanguageToggle />
              <CurrencyMenu />
              <AccountMenu />
            </div>
          </header>
          <main id="main-content" tabIndex={-1} className="flex-1 p-4 outline-none sm:p-6 lg:p-8">
            <div className="mx-auto max-w-[1400px]">{children}</div>
          </main>
        </div>
      </div>
    </div>
  );
}