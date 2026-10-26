"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  Activity,
  LayoutDashboard,
  Lightbulb,
  CirclePlus,
  Menu,
  MessagesSquare,
  PackageX,
  Sparkles,
  TrendingUp,
  Upload,
  Users,
  Wallet,
  X,
  Grid3x3,
  Truck,
  Banknote,
  CalendarClock,
  Rocket,
  Telescope,
  BookUser,
  Eye,
  Palette,
  Calculator,
  Flag,
  ClipboardCheck,
  Boxes,
  UserPlus,
  Undo2,
  LifeBuoy,
  MessageSquareText,
  PiggyBank,
  Workflow,
  ScrollText,
  Mail,
  PhoneCall,
  ShoppingCart,
  Send,
  ShieldCheck,
  FileText,
  Inbox,
  Video,
  Megaphone,
  Route,
  BarChart3,
  Settings,
} from "lucide-react";
import { AccountMenu } from "@/components/layout/account-menu";
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
      { href: "/revenue", label: "Revenue Intelligence", icon: TrendingUp },
      { href: "/order-risk", label: "Order Risk", icon: PackageX },
      { href: "/models", label: "Model Report Card", icon: ClipboardCheck },
      { href: "/couriers", label: "Courier Scorecard", icon: Truck },
      { href: "/cash", label: "Cash Tracker", icon: Banknote },
      { href: "/profit", label: "Real Profit", icon: PiggyBank },
      { href: "/meta-ads", label: "Meta Ads", icon: Megaphone },
      { href: "/seasons", label: "Season Forecast", icon: CalendarClock },
    ],
  },
  {
    label: "Launch Studio",
    items: [
      { href: "/launch", label: "Launch projects", icon: Rocket },
      { href: "/launch/trends", label: "Trend Finder", icon: Telescope },
      { href: "/launch/vendors", label: "Vendor Book", icon: BookUser },
      { href: "/launch/competitors", label: "Competitor Board", icon: Eye },
      { href: "/launch/creatives", label: "Creative Studio", icon: Palette },
      { href: "/launch/profit", label: "Profit Check", icon: Calculator },
      { href: "/launch/finish", label: "Launch", icon: Flag },
    ],
  },
  {
    label: "Auto Messenger",
    items: [
      { href: "/messenger/settings", label: "Messenger Settings", icon: Settings },
      { href: "/messenger/templates", label: "Templates", icon: FileText },
      { href: "/messenger/consent", label: "Consent", icon: ShieldCheck },
      { href: "/inbox", label: "Inbox", icon: MessageSquareText },
      { href: "/messenger/messages", label: "Messages", icon: Inbox },
      { href: "/messenger/orders", label: "Order Updates", icon: Send },
      { href: "/messenger/cod", label: "COD Confirmation", icon: PhoneCall },
      { href: "/email-automations", label: "Email Automations", icon: Mail },
      { href: "/messenger/carts", label: "Abandoned Carts", icon: ShoppingCart },
      { href: "/messenger/videos", label: "Customer Videos", icon: Video },
      { href: "/messenger/campaigns", label: "Announcements", icon: Megaphone },
      { href: "/messenger/journeys", label: "Journeys", icon: Route },
      { href: "/messenger/results", label: "Messaging Results", icon: BarChart3 },
    ],
  },
  {
    label: "Automation",
    items: [
      { href: "/workflows", label: "Workflows", icon: Workflow },
      { href: "/workflows/runs", label: "Workflow Logs", icon: ScrollText },
    ],
  },
  {
    label: "Actions",
    items: [
      { href: "/recommendations", label: "Recommendations", icon: Lightbulb },
    ],
  },
  {
    label: "Data",
    items: [
      { href: "/orders/new", label: "Add Order", icon: CirclePlus },
      { href: "/leads", label: "Leads", icon: UserPlus },
      { href: "/returns", label: "Returns and Refunds", icon: Undo2 },
      { href: "/tickets", label: "Complaints", icon: LifeBuoy },
      { href: "/inventory", label: "Inventory", icon: Boxes },
      { href: "/import", label: "Import Data", icon: Upload },
      { href: "/import/whatsapp", label: "Import WhatsApp Chat", icon: MessagesSquare },
    ],
  },
];

function isActive(pathname: string, href: string) {
  // "/", "/import" and "/launch" only match themselves, because "/import/whatsapp" and "/launch/trends" have their own menu items.
  return href === "/" || href === "/import" || href === "/launch" || href === "/workflows" ? pathname === href : pathname.startsWith(href);
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
    <div className="min-h-full bg-app text-ink">
      <a
        href="#main-content"
        className="sr-only z-50 rounded-lg bg-surface px-3 py-2 text-sm font-medium text-accent shadow focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Skip to content
      </a>
      <div className="flex min-h-screen">
        {open ? (
          <div
            className="fixed inset-0 z-30 bg-slate-900/50 lg:hidden"
            aria-hidden="true"
            onClick={() => closeDrawer()}
          />
        ) : null}
        <aside
          id="app-sidebar"
          inert={drawerHidden}
          className={cn(
            "theme-sidebar fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-line bg-sidebar text-ink-2 transition-transform duration-200 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0",
            open ? "translate-x-0" : "-translate-x-full",
          )}
        >
          <div className="flex items-center justify-between px-5 py-5">
            <Link href="/" className="flex items-center gap-2" onClick={() => closeDrawer(false)}>
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-sm font-bold text-accent-ink">
                IQ
              </span>
              <span>
                <span className="block text-sm font-semibold text-ink">CustomerIQ AI</span>
                <span className="block text-[11px] text-faint">Predictive customer intelligence</span>
              </span>
            </Link>
            <button
              ref={closeButtonRef}
              type="button"
              className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink lg:hidden"
              onClick={() => closeDrawer()}
              aria-label="Close navigation"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <nav aria-label="Main" className="flex-1 space-y-5 overflow-y-auto px-3 pb-3">
            {navGroups.map((group) => (
              <div key={group.label}>
                <p className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted">
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
                            "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
                            active
                              ? "bg-accent/15 font-medium text-accent-strong"
                              : "text-muted hover:bg-surface-2 hover:text-ink",
                          )}
                        >
                          <item.icon className="h-4 w-4" aria-hidden="true" />
                          {item.label}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>
          <div className="m-3 rounded-xl border border-line bg-surface p-3 text-xs text-muted">
            <p className="flex items-center gap-1 font-medium text-ink-2">
              <Sparkles className="h-3.5 w-3.5 text-accent" aria-hidden="true" />
              {(LIVE ? "Live workspace" : "Demo workspace")}
            </p>
            <p className="mt-1">
              {(LIVE ? "Dashboards use your imported data. Predictions appear only when a model passed its accuracy test." : "No backend configured. Dashboards show sample data.")}
            </p>
          </div>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-line bg-surface px-4 py-3">
            <button
              ref={menuButtonRef}
              type="button"
              className="rounded-lg p-2 hover:bg-surface-3 lg:hidden"
              onClick={openDrawer}
              aria-label="Open navigation"
              aria-expanded={open}
              aria-controls="app-sidebar"
            >
              <Menu className="h-5 w-5" />
            </button>
            <p className="min-w-0 truncate text-sm font-medium text-ink lg:hidden">{currentLabel}</p>
            <p className="hidden text-sm text-muted lg:block">
              Customer intelligence for e-commerce stores
            </p>
            <div className="ml-auto flex items-center gap-2 sm:gap-3">
              <span
                className={cn(
                  "hidden rounded-full px-2.5 py-1 text-xs font-medium sm:inline",
                  LIVE ? "bg-success/10 text-success" : "bg-warning/10 text-warning",
                )}
              >
                {(LIVE ? "Live data" : "Demo data")}
              </span>
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