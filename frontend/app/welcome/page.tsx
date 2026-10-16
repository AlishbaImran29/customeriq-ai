import type { Metadata } from "next";
import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Bot,
  Check,
  FlaskConical,
  Grid3x3,
  HeartPulse,
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
    text: "What each customer and segment has spent so far, and what they are expected to spend next.",
  },
  {
    icon: HeartPulse,
    title: "Health scores",
    text: "One 0–100 score per customer from purchase frequency, spending, engagement, and activity trends.",
  },
  {
    icon: TrendingUp,
    title: "Revenue intelligence",
    text: "Trends, a forecast, what drives revenue by channel and country, and how much is at risk.",
  },
  {
    icon: Grid3x3,
    title: "Cohort retention",
    text: "How many customers from each first-order month come back, month after month.",
  },
  {
    icon: UserRound,
    title: "Customer pages",
    text: "Open any customer to see their orders, their health, and the action we recommend.",
  },
  {
    icon: Bot,
    title: "Ask in plain language",
    text: "An optional assistant answers questions about your own data, such as who is going quiet.",
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
    text: "Dashboards fill in at once. Pick any date range, switch currency, or read it in your own language.",
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
  { name: "Champions", share: 24, color: "bg-teal-400" },
  { name: "Loyal", share: 31, color: "bg-teal-500" },
  { name: "Potential", share: 18, color: "bg-sky-400" },
  { name: "At-Risk", share: 17, color: "bg-amber-400" },
  { name: "Lost", share: 10, color: "bg-rose-400" },
];

function Logo() {
  return (
    <Link href="/welcome" className="flex items-center gap-2">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal-500 text-sm font-bold text-slate-950">IQ</span>
      <span className="text-sm font-semibold text-white">CustomerIQ AI</span>
    </Link>
  );
}

/** A drawn picture of the dashboard. Every number in it is a made-up example. */
function DashboardPreview() {
  return (
    <figure className="relative mx-auto w-full max-w-xl">
      <div className="absolute -inset-4 rounded-[2rem] bg-teal-500/20 blur-2xl" aria-hidden="true" />
      <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-slate-900/80 shadow-2xl ring-1 ring-white/5 backdrop-blur" aria-hidden="true">
        <div className="flex items-center gap-1.5 border-b border-white/10 px-4 py-3">
          <span className="h-2.5 w-2.5 rounded-full bg-rose-400/80" />
          <span className="h-2.5 w-2.5 rounded-full bg-amber-400/80" />
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/80" />
          <span className="ml-3 text-xs text-slate-400">Customer Intelligence Dashboard</span>
        </div>
        <div className="space-y-4 p-4">
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Revenue", value: "$48.2k", delta: "+8.4%" },
              { label: "Retention", value: "62%", delta: "+3 pts" },
              { label: "Growth score", value: "71/100", delta: "" },
            ].map((kpi) => (
              <div key={kpi.label} className="rounded-xl border border-white/10 bg-white/5 p-3">
                <p className="text-[10px] uppercase tracking-wide text-slate-400">{kpi.label}</p>
                <p className="mt-1 text-lg font-semibold text-white">{kpi.value}</p>
                <p className="text-[11px] text-emerald-400">{kpi.delta || " "}</p>
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5 p-3">
            <p className="text-[11px] text-slate-400">Monthly revenue</p>
            <div className="mt-3 flex h-28 items-end gap-1.5">
              {bars.map((height, index) => (
                <span
                  key={index}
                  style={{ height: `${height}%` }}
                  className={index > 8 ? "flex-1 rounded-t bg-teal-300/60" : "flex-1 rounded-t bg-teal-400"}
                />
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5 p-3">
            <p className="text-[11px] text-slate-400">Customer segments</p>
            <div className="mt-3 flex h-3 overflow-hidden rounded-full">
              {segments.map((segment) => (
                <span key={segment.name} style={{ width: `${segment.share}%` }} className={segment.color} />
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
              {segments.map((segment) => (
                <span key={segment.name} className="flex items-center gap-1.5 text-[11px] text-slate-300">
                  <span className={`h-2 w-2 rounded-full ${segment.color}`} />
                  {segment.name}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
      <figcaption className="mt-3 text-center text-xs text-slate-500">An illustration with example numbers, not real data.</figcaption>
    </figure>
  );
}

export default function WelcomePage() {
  return (
    <div className="min-h-screen bg-white text-slate-900">
      <header className="absolute inset-x-0 top-0 z-20">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5">
          <Logo />
          <nav aria-label="Main" className="hidden items-center gap-7 text-sm text-slate-300 md:flex">
            <a href="#features" className="hover:text-white">Features</a>
            <a href="#how" className="hover:text-white">How it works</a>
            <a href="#honest" className="hover:text-white">Why trust it</a>
          </nav>
          <div className="flex items-center gap-2">
            <Link href="/login" className="rounded-xl px-3.5 py-2 text-sm font-medium text-slate-200 hover:text-white">
              Sign in
            </Link>
            <Link href="/login" className="rounded-xl bg-teal-500 px-3.5 py-2 text-sm font-semibold text-slate-950 hover:bg-teal-400">
              Get started
            </Link>
          </div>
        </div>
      </header>

      <main>
        <section className="relative overflow-hidden bg-slate-950 pb-20 pt-32 text-white sm:pb-28 sm:pt-40">
          <div
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(60rem_40rem_at_70%_-10%,rgba(20,184,166,0.25),transparent),radial-gradient(40rem_30rem_at_0%_100%,rgba(14,165,233,0.12),transparent)]"
            aria-hidden="true"
          />
          <div className="relative mx-auto grid max-w-6xl items-center gap-14 px-5 lg:grid-cols-2">
            <div>
              <p className="inline-flex items-center gap-2 rounded-full border border-teal-400/30 bg-teal-400/10 px-3 py-1 text-xs font-medium text-teal-200">
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                Customer intelligence for online stores
              </p>
              <h1 className="mt-5 text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl lg:text-[3.4rem]">
                Know which customers to <span className="text-teal-300">keep, grow,</span> and win back.
              </h1>
              <p className="mt-5 max-w-xl text-base leading-relaxed text-slate-300 sm:text-lg">
                Import your orders and CustomerIQ AI turns them into customer segments, churn risk, lifetime value, and
                revenue insights, with predictions shown only when they are accurate enough to trust.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 rounded-xl bg-teal-500 px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-teal-500/20 hover:bg-teal-400"
                >
                  Get started
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
                <a href="#how" className="rounded-xl border border-white/15 px-5 py-3 text-sm font-medium text-slate-100 hover:bg-white/5">
                  See how it works
                </a>
              </div>
              <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-400">
                {["CSV, Excel, and Shopify exports", "12 languages", "Multiple currencies"].map((item) => (
                  <li key={item} className="flex items-center gap-1.5">
                    <Check className="h-4 w-4 text-teal-400" aria-hidden="true" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <DashboardPreview />
          </div>
        </section>

        <section id="features" className="scroll-mt-20 bg-slate-50 py-20 sm:py-24">
          <div className="mx-auto max-w-6xl px-5">
            <div className="mx-auto max-w-2xl text-center">
              <p className="text-sm font-semibold text-teal-700">What you get</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Everything about your customers, in one place</h2>
              <p className="mt-3 text-slate-600">From a first look at who buys, to a plan for who to talk to this week.</p>
            </div>
            <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {features.map((feature) => (
                <div key={feature.title} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-50 text-teal-700">
                    <feature.icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <h3 className="mt-4 font-semibold text-slate-900">{feature.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{feature.text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="how" className="scroll-mt-20 bg-white py-20 sm:py-24">
          <div className="mx-auto max-w-6xl px-5">
            <div className="mx-auto max-w-2xl text-center">
              <p className="text-sm font-semibold text-teal-700">How it works</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">From a file to a plan in three steps</h2>
            </div>
            <ol className="mt-12 grid gap-8 md:grid-cols-3">
              {steps.map((step, index) => (
                <li key={step.title} className="relative rounded-2xl border border-slate-200 bg-slate-50 p-6">
                  <span className="absolute -top-4 left-6 flex h-8 w-8 items-center justify-center rounded-full bg-teal-600 text-sm font-semibold text-white">
                    {index + 1}
                  </span>
                  <step.icon className="mt-2 h-6 w-6 text-teal-700" aria-hidden="true" />
                  <h3 className="mt-3 font-semibold text-slate-900">{step.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{step.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="honest" className="scroll-mt-20 bg-slate-950 py-20 text-white sm:py-24">
          <div className="mx-auto max-w-6xl px-5">
            <div className="mx-auto max-w-2xl text-center">
              <p className="inline-flex items-center gap-2 text-sm font-semibold text-teal-300">
                <FlaskConical className="h-4 w-4" aria-hidden="true" />
                Why you can trust it
              </p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Honest by design</h2>
              <p className="mt-3 text-slate-300">
                Dashboards that always show a confident number are easy to build. We would rather tell you when we do not know.
              </p>
            </div>
            <div className="mt-12 grid gap-5 sm:grid-cols-2">
              {promises.map((promise) => (
                <div key={promise.title} className="rounded-2xl border border-white/10 bg-white/5 p-6">
                  <h3 className="flex items-start gap-2 font-semibold">
                    <Check className="mt-0.5 h-5 w-5 shrink-0 text-teal-400" aria-hidden="true" />
                    {promise.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-300">{promise.text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="bg-gradient-to-br from-teal-600 to-teal-700 py-16 text-white">
          <div className="mx-auto flex max-w-4xl flex-col items-center px-5 text-center">
            <Lock className="h-6 w-6 text-teal-200" aria-hidden="true" />
            <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Ready to see your customers clearly?</h2>
            <p className="mt-3 max-w-xl text-teal-50">Sign in, import your orders, and your dashboards fill in within moments.</p>
            <Link href="/login" className="mt-7 inline-flex items-center gap-2 rounded-xl bg-white px-6 py-3 text-sm font-semibold text-teal-800 shadow-lg hover:bg-teal-50">
              Get started
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </section>
      </main>

      <footer className="bg-slate-950 py-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-5 text-xs text-slate-500 sm:flex-row">
          <Logo />
          <p>Predictions are estimates based on your past orders, not guarantees.</p>
          <Link href="/login" className="hover:text-slate-300">Sign in</Link>
        </div>
      </footer>
    </div>
  );
}
