import type { Metadata } from "next";
import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Check,
  FlaskConical,
  Grid3x3,
  Lock,
  Sparkles,
  TrendingUp,
  Upload,
  UserRound,
  Users,
  Wallet,
} from "lucide-react";

export const metadata: Metadata = {
  title: "CustomerIQ AI: know which customers to keep, grow, and win back",
  description:
    "Import your orders and get customer segments, churn risk, lifetime value, and revenue insights. Predictions appear only when they are accurate enough to trust.",
};

const features = [
  {
    icon: Users,
    title: "Customer segments",
    text: "Customers grouped by how recently, how often, and how much they buy: Champions, Loyal, At-Risk, Lost, and more.",
  },
  {
    icon: Activity,
    title: "Churn risk",
    text: "See who is likely to stop buying, with a risk level and a suggested next step for each customer.",
  },
  {
    icon: Wallet,
    title: "Lifetime value",
    text: "What each customer and segment has spent with you so far.",
  },
  {
    icon: TrendingUp,
    title: "Revenue intelligence",
    text: "Revenue trends, revenue by country, and how much revenue is at risk.",
  },
  {
    icon: Grid3x3,
    title: "Cohort retention",
    text: "How many customers from each first-order month come back, month after month.",
  },
  {
    icon: UserRound,
    title: "Customer pages",
    text: "Open any customer to see their orders, their churn risk, and the action we recommend.",
  },
];

const steps = [
  {
    icon: Upload,
    title: "Import your orders",
    text: "Upload a CSV, Excel, or Shopify order export. Every row is checked, and rejected rows are listed with the reason.",
  },
  {
    icon: Sparkles,
    title: "See your customers clearly",
    text: "Dashboards fill in at once. Pick any date range and see every customer's segment and churn risk.",
  },
  {
    icon: ArrowRight,
    title: "Act on it",
    text: "Follow the recommended action for each segment, and download the customer list as a CSV for your team.",
  },
];

const promises = [
  {
    title: "Predictions have to earn their place",
    text: "A model is shown only after it passes a test on past data and beats a simple baseline. Otherwise you see “not available yet” and the reason.",
  },
  {
    title: "No made-up numbers",
    text: "Missing data stays missing. We never fill gaps with invented values or sample charts in your live data.",
  },
  {
    title: "Methods you can read",
    text: "Scores such as the Growth Score come with a breakdown of their inputs and weights, so you can see why a number is what it is.",
  },
  {
    title: "Private by default",
    text: "Everything sits behind sign-in, in a database you control.",
  },
];

const bars = [38, 45, 41, 52, 58, 55, 63, 70, 66, 78, 84, 92];
const segments = [
  { name: "Champions", share: 24, color: "bg-accent" },
  { name: "Loyal", share: 31, color: "bg-accent" },
  { name: "Potential", share: 18, color: "bg-info" },
  { name: "At-Risk", share: 17, color: "bg-warning" },
  { name: "Lost", share: 10, color: "bg-danger" },
];

function Logo() {
  return (
    <Link href="/welcome" className="flex items-center gap-2">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-sm font-bold text-accent-ink">IQ</span>
      <span className="text-sm font-semibold text-white">CustomerIQ AI</span>
    </Link>
  );
}

/** A drawn picture of the dashboard. Every number in it is a made-up example. */
function DashboardPreview() {
  return (
    <figure className="relative mx-auto w-full max-w-xl">
      <div className="absolute -inset-4 rounded-[2rem] bg-accent/20 blur-2xl" aria-hidden="true" />
      <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-surface/80 shadow-2xl ring-1 ring-white/5 backdrop-blur" aria-hidden="true">
        <div className="flex items-center gap-1.5 border-b border-white/10 px-4 py-3">
          <span className="h-2.5 w-2.5 rounded-full bg-danger/80" />
          <span className="h-2.5 w-2.5 rounded-full bg-warning/80" />
          <span className="h-2.5 w-2.5 rounded-full bg-success/80" />
          <span className="ml-3 text-xs text-faint">Customer Intelligence Dashboard</span>
        </div>
        <div className="space-y-4 p-4">
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Revenue", value: "£48.2k", delta: "+8.4%" },
              { label: "Retention", value: "62%", delta: "+3 pts" },
              { label: "Growth score", value: "71/100", delta: "" },
            ].map((kpi) => (
              <div key={kpi.label} className="rounded-xl border border-white/10 bg-white/5 p-3">
                <p className="text-[10px] uppercase tracking-wide text-faint">{kpi.label}</p>
                <p className="mt-1 text-lg font-semibold text-white">{kpi.value}</p>
                <p className="text-[11px] text-success">{kpi.delta || " "}</p>
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5 p-3">
            <p className="text-[11px] text-faint">Monthly revenue</p>
            <div className="mt-3 flex h-28 items-end gap-1.5">
              {bars.map((height, index) => (
                <span
                  key={index}
                  style={{ height: `${height}%` }}
                  className="flex-1 rounded-t bg-accent"
                />
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5 p-3">
            <p className="text-[11px] text-faint">Customer segments</p>
            <div className="mt-3 flex h-3 overflow-hidden rounded-full">
              {segments.map((segment) => (
                <span key={segment.name} style={{ width: `${segment.share}%` }} className={segment.color} />
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
              {segments.map((segment) => (
                <span key={segment.name} className="flex items-center gap-1.5 text-[11px] text-faint">
                  <span className={`h-2 w-2 rounded-full ${segment.color}`} />
                  {segment.name}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
      <figcaption className="mt-3 text-center text-xs text-muted">An illustration with example numbers, not real data.</figcaption>
    </figure>
  );
}

export default function WelcomePage() {
  return (
    <div className="min-h-screen bg-app text-ink">
      <header className="absolute inset-x-0 top-0 z-20">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5">
          <Logo />
          <nav aria-label="Main" className="hidden items-center gap-7 text-sm text-faint md:flex">
            <a href="#features" className="hover:text-white">Features</a>
            <a href="#how" className="hover:text-white">How it works</a>
            <a href="#honest" className="hover:text-white">Why trust it</a>
          </nav>
          <div className="flex items-center gap-2">
            <Link href="/login" className="rounded-xl px-3.5 py-2 text-sm font-medium text-ink-2 hover:text-white">
              Sign in
            </Link>
            <Link href="/login?mode=signup" className="rounded-xl bg-accent px-3.5 py-2 text-sm font-semibold text-accent-ink hover:bg-accent-strong">
              Get started
            </Link>
          </div>
        </div>
      </header>

      <main>
        <section className="relative overflow-hidden bg-sidebar pb-20 pt-32 text-white sm:pb-28 sm:pt-40">
          <div
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(60rem_40rem_at_70%_-10%,rgba(20,184,166,0.25),transparent),radial-gradient(40rem_30rem_at_0%_100%,rgba(14,165,233,0.12),transparent)]"
            aria-hidden="true"
          />
          <div className="relative mx-auto grid max-w-6xl items-center gap-14 px-5 lg:grid-cols-2">
            <div>
              <p className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-3 py-1 text-xs font-medium text-accent-strong">
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                Customer intelligence for online stores
              </p>
              <h1 className="mt-5 text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl lg:text-[3.4rem]">
                Know which customers to <span className="text-accent">keep, grow,</span> and win back.
              </h1>
              <p className="mt-5 max-w-xl text-base leading-relaxed text-faint sm:text-lg">
                Import your orders and CustomerIQ AI turns them into customer segments, churn risk, lifetime value, and
                revenue insights, with predictions shown only when they are accurate enough to trust.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Link
                  href="/login?mode=signup"
                  className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-3 text-sm font-semibold text-accent-ink shadow-lg shadow-accent/20 hover:bg-accent-strong"
                >
                  Get started
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
                <a href="#how" className="rounded-xl border border-white/15 px-5 py-3 text-sm font-medium text-ink hover:bg-white/5">
                  See how it works
                </a>
              </div>
              <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-faint">
                {["CSV, Excel, and Shopify exports", "Predictions only when they beat a baseline"].map((item) => (
                  <li key={item} className="flex items-center gap-1.5">
                    <Check className="h-4 w-4 text-accent" aria-hidden="true" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <DashboardPreview />
          </div>
        </section>

        <section id="features" className="scroll-mt-20 bg-surface-2 py-20 sm:py-24">
          <div className="mx-auto max-w-6xl px-5">
            <div className="mx-auto max-w-2xl text-center">
              <p className="text-sm font-semibold text-accent">What you get</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Everything about your customers, in one place</h2>
              <p className="mt-3 text-ink-2">From a first look at who buys, to a plan for who to talk to this week.</p>
            </div>
            <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {features.map((feature) => (
                <div key={feature.title} className="rounded-2xl border border-line bg-surface p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/10 text-accent">
                    <feature.icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <h3 className="mt-4 font-semibold text-ink">{feature.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{feature.text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="how" className="scroll-mt-20 bg-surface py-20 sm:py-24">
          <div className="mx-auto max-w-6xl px-5">
            <div className="mx-auto max-w-2xl text-center">
              <p className="text-sm font-semibold text-accent">How it works</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">From a file to a plan in three steps</h2>
            </div>
            <ol className="mt-12 grid gap-8 md:grid-cols-3">
              {steps.map((step, index) => (
                <li key={step.title} className="relative rounded-2xl border border-line bg-surface-2 p-6">
                  <span className="absolute -top-4 left-6 flex h-8 w-8 items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-ink">
                    {index + 1}
                  </span>
                  <step.icon className="mt-2 h-6 w-6 text-accent" aria-hidden="true" />
                  <h3 className="mt-3 font-semibold text-ink">{step.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{step.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="honest" className="scroll-mt-20 bg-sidebar py-20 text-white sm:py-24">
          <div className="mx-auto max-w-6xl px-5">
            <div className="mx-auto max-w-2xl text-center">
              <p className="inline-flex items-center gap-2 text-sm font-semibold text-accent">
                <FlaskConical className="h-4 w-4" aria-hidden="true" />
                Why you can trust it
              </p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Honest by design</h2>
              <p className="mt-3 text-faint">
                Dashboards that always show a confident number are easy to build. We would rather tell you when we do not know.
              </p>
            </div>
            <div className="mt-12 grid gap-5 sm:grid-cols-2">
              {promises.map((promise) => (
                <div key={promise.title} className="rounded-2xl border border-white/10 bg-white/5 p-6">
                  <h3 className="flex items-start gap-2 font-semibold">
                    <Check className="mt-0.5 h-5 w-5 shrink-0 text-accent" aria-hidden="true" />
                    {promise.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-faint">{promise.text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="bg-gradient-to-br from-accent to-teal py-16 text-accent-ink">
          <div className="mx-auto flex max-w-4xl flex-col items-center px-5 text-center">
            <Lock className="h-6 w-6 text-accent-strong" aria-hidden="true" />
            <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Ready to see your customers clearly?</h2>
            <p className="mt-3 max-w-xl text-accent-ink">Sign in, import your orders, and your dashboards fill in within moments.</p>
            <Link href="/login?mode=signup" className="mt-7 inline-flex items-center gap-2 rounded-xl bg-app px-6 py-3 text-sm font-semibold text-accent shadow-lg hover:bg-sidebar">
              Get started
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </section>
      </main>

      <footer className="bg-sidebar py-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-5 text-xs text-muted sm:flex-row">
          <Logo />
          <p>Predictions are estimates based on your past orders, not guarantees.</p>
          <Link href="/login" className="hover:text-faint">Sign in</Link>
        </div>
      </footer>
    </div>
  );
}
