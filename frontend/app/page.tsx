import Link from "next/link";
import {
  ArrowRight,
  Activity,
  BrainCircuit,
  CalendarClock,
  CheckCircle2,
  Cloud,
  Droplet,
  Languages,
  LogIn,
  MessageSquareText,
  Network,
  Play,
  ShieldCheck,
  Sparkles,
  UserPlus,
} from "lucide-react";

import { MarketingFooter } from "@/components/marketing/footer";
import { MarketingNav } from "@/components/marketing/nav";
import { AnimatedCounter } from "@/components/ui/animated-counter";
import { Reveal } from "@/components/ui/reveal";

const DIFFERENTIATORS = [
  {
    icon: BrainCircuit,
    title: "Cohort Stability ML",
    tag: "Differentiator #1",
    body:
      "XGBoost classifiers predict 30/60/90-day churn for every donor. SHAP explains exactly why — so coordinators see 'response rate 32%, last donation 120 days ago' instead of a black box.",
    href: "/bridges",
    link_label: "Inspect a cohort →",
  },
  {
    icon: CalendarClock,
    title: "OR-Tools Rotation Scheduler",
    tag: "Differentiator #2",
    body:
      "A CP-SAT solver assigns every transfusion in the next 12 months to one donor under the 90-day deferral rule + cadence + load balancing — in about 50 ms.",
    href: "/bridges",
    link_label: "See a schedule →",
  },
  {
    icon: Play,
    title: "Live Cohort Simulator",
    tag: "Differentiator #3",
    body:
      "Click any donor to eject them. The system re-runs stability ML, the scheduler, and the recommender in real time and tells you exactly how cohort health changed.",
    href: "/simulator",
    link_label: "Run a scenario →",
  },
  {
    icon: Sparkles,
    title: "Multilingual Care Agent",
    tag: "Differentiator #4",
    body:
      "Coordinators ask in any of 8 Indian languages. The agent assembles per-entity memory and answers grounded in live data — AWS Bedrock multi-model (Claude Sonnet + Haiku + Titan v2) when configured, deterministic fallback otherwise.",
    href: "/agent",
    link_label: "Talk to the agent →",
  },
];

type ImpactStat = {
  label: string;
  // Either a static value or an animated counter (`numeric` is what AnimatedCounter targets)
  value?: string;
  numeric?: { target: number; prefix?: string; suffix?: string };
};

const IMPACT_STATS: ImpactStat[] = [
  {
    label: "thalassemia patients in India",
    numeric: { target: 100, prefix: "~", suffix: "K" },
  },
  {
    label: "transfusion cadence per patient",
    numeric: { target: 18, prefix: "every ", suffix: "d" },
  },
  { value: "8–10", label: "donors per Blood Bridge cohort" },
  { value: "1 patient", label: "one bridge — for years" },
];

const HOW_IT_WORKS = [
  {
    n: "01",
    icon: Activity,
    title: "Stability triage",
    body:
      "ML scores every donor's churn risk every morning. At-risk cohorts surface to the Recommendations inbox automatically.",
  },
  {
    n: "02",
    icon: Network,
    title: "Recruit a replacement",
    body:
      "The recommender ranks nearby compatible donors by distance + response rate + predicted churn. Kell-negative match gets a +10% bonus for repeat-transfused patients.",
  },
  {
    n: "03",
    icon: MessageSquareText,
    title: "Reach donors in their language",
    body:
      "WhatsApp templates auto-fill the patient + donor names. The Care Agent drafts personalised messages in Hindi, Telugu, Tamil, Marathi, Bengali, Kannada, or Gujarati.",
  },
];

export default function HomePage() {
  return (
    <div className="min-h-screen bg-background text-white">
      <MarketingNav />

      {/* ---- Hero ---- */}
      <section className="relative overflow-hidden border-b border-white/5 px-6 pb-24 pt-16 sm:pt-24">
        {/* Aurora — two animated radial orbs behind the hero text */}
        <div
          aria-hidden
          data-testid="aurora-backdrop"
          className="pointer-events-none absolute inset-0 -z-10 overflow-hidden"
        >
          <div
            className="aurora-orb aurora-orb-a"
            style={{ left: "10%", top: "-10%", width: "55vw", height: "55vw", maxWidth: "720px", maxHeight: "720px" }}
          />
          <div
            className="aurora-orb aurora-orb-b"
            style={{ right: "5%", top: "0%", width: "50vw", height: "50vw", maxWidth: "660px", maxHeight: "660px" }}
          />
          {/* Centred soft wash that keeps text contrast */}
          <div
            className="absolute inset-0 opacity-60"
            style={{
              background:
                "radial-gradient(60% 60% at 50% 0%, rgba(10,15,30,0.0) 0%, rgba(10,15,30,0.55) 60%, rgba(10,15,30,0.95) 100%)",
            }}
          />
        </div>

        <div className="mx-auto max-w-5xl text-center">
          <div className="mx-auto inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/60">
            <Droplet className="h-3 w-3 text-primary" />
            <span>AI for Good Hackathon 2026 · Blood Warriors track</span>
          </div>

          <h1 className="mt-6 bg-gradient-to-r from-primary via-white to-accent bg-clip-text text-5xl font-bold leading-[1.05] tracking-tight text-transparent sm:text-7xl">
            Bridge OS
          </h1>

          <p className="mx-auto mt-6 max-w-3xl text-xl text-white/80 sm:text-2xl">
            The operating system for Blood Bridges.
          </p>

          <p className="mx-auto mt-4 max-w-3xl text-base text-white/55">
            Thalassemia patients need a transfusion every 18 days for life. Blood
            Warriors organises 8–10 voluntary donors per patient into cohorts
            that recur-donate for years. Bridge OS is the AI layer that keeps
            those cohorts healthy at national scale.
          </p>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/login?next=%2Fdashboard"
              data-testid="hero-cta-primary"
              className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-primary/30 transition-colors hover:bg-primary-600"
            >
              <LogIn className="h-4 w-4" />
              Sign in to the dashboard
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/how-it-works"
              data-testid="hero-cta-secondary"
              className="inline-flex items-center gap-2 rounded-full border border-white/15 px-6 py-3 text-sm font-medium text-white/80 transition-colors hover:border-white/30 hover:text-white"
            >
              See how it works
            </Link>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-xs text-white/55">
            <span>New here?</span>
            <Link
              href="/signup"
              data-testid="hero-cta-signup"
              className="inline-flex items-center gap-1 rounded-full bg-primary/15 px-3 py-1 font-medium text-primary ring-1 ring-primary/30 hover:bg-primary/25"
            >
              <UserPlus className="h-3 w-3" />
              Sign up (donor or patient)
            </Link>
          </div>

          {/* Judge / reviewer demo credentials — prominently surfaced so
              hackathon reviewers can explore the full dashboard immediately
              without going through the donor/patient signup flow. The
              account is in the `admins` Cognito group so every page is
              visible. */}
          <div
            data-testid="judge-credentials-card"
            className="mx-auto mt-10 max-w-2xl rounded-2xl border border-amber-400/30 bg-gradient-to-br from-amber-500/10 via-amber-400/5 to-orange-500/10 p-5 text-left"
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-amber-300/90">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  Hackathon reviewer access
                </div>
                <p className="mt-1 text-sm text-white/80">
                  The dashboard is auth-gated. Use the account below for full
                  admin access to every page — donor list, ML cohort health,
                  simulator, WhatsApp panel, automation engine and the live
                  demo button.
                </p>
              </div>
              <Link
                href="/login?next=%2Fdashboard"
                className="hidden shrink-0 items-center gap-2 rounded-full bg-amber-400/90 px-4 py-2 text-sm font-semibold text-black hover:bg-amber-300 sm:inline-flex"
              >
                Sign in
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-white/5 bg-black/30 p-3 font-mono text-xs">
                <p className="text-[10px] uppercase tracking-wider text-white/40">
                  email
                </p>
                <p
                  data-testid="judge-credentials-email"
                  className="mt-1 text-white"
                >
                  gunapavan4321@gmail.com
                </p>
              </div>
              <div className="rounded-lg border border-white/5 bg-black/30 p-3 font-mono text-xs">
                <p className="text-[10px] uppercase tracking-wider text-white/40">
                  password
                </p>
                <p
                  data-testid="judge-credentials-password"
                  className="mt-1 text-white"
                >
                  Admin@123#
                </p>
              </div>
            </div>
          </div>

          {/* Impact strip */}
          <div className="mx-auto mt-16 grid max-w-4xl grid-cols-2 gap-4 sm:grid-cols-4">
            {IMPACT_STATS.map((s) => (
              <div
                key={s.label}
                data-testid="impact-stat"
                className="rounded-xl border border-white/5 bg-surface/40 px-4 py-5"
              >
                <p className="bg-gradient-to-r from-primary to-accent bg-clip-text text-2xl font-bold text-transparent">
                  {s.numeric ? (
                    <>
                      {s.numeric.prefix}
                      <AnimatedCounter value={s.numeric.target} />
                      {s.numeric.suffix}
                    </>
                  ) : (
                    s.value
                  )}
                </p>
                <p className="mt-1 text-[11px] uppercase tracking-wider text-white/40">
                  {s.label}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---- Differentiators ---- */}
      <section className="border-b border-white/5 px-6 py-24">
        <div className="mx-auto max-w-6xl">
          <div className="mb-12 text-center">
            <p className="text-xs uppercase tracking-widest text-accent">
              Four working AI systems
            </p>
            <h2 className="mt-3 text-3xl font-bold sm:text-4xl">
              Not a wireframe — a working product
            </h2>
            <p className="mx-auto mt-3 max-w-2xl text-sm text-white/60">
              Every panel below is live and clickable. Each links into the
              dashboard where the underlying model runs against live data.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            {DIFFERENTIATORS.map((d, i) => {
              const Icon = d.icon;
              return (
                <Reveal
                  key={d.title}
                  delay={i * 0.08}
                  data-testid="differentiator-card"
                  className="group relative overflow-hidden rounded-2xl border border-white/5 bg-surface/40 p-6 transition-colors hover:border-white/15"
                >
                  <div className="mb-3 flex items-start justify-between">
                    <div className="rounded-lg bg-primary/10 p-2.5 ring-1 ring-primary/20">
                      <Icon className="h-5 w-5 text-primary" />
                    </div>
                    <span className="rounded-full border border-accent/20 bg-accent/5 px-2.5 py-0.5 text-[10px] uppercase tracking-wider text-accent">
                      {d.tag}
                    </span>
                  </div>
                  <h3 className="text-xl font-semibold">{d.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-white/65">
                    {d.body}
                  </p>
                  <Link
                    href={d.href}
                    className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary opacity-80 transition-opacity group-hover:opacity-100"
                  >
                    {d.link_label}
                  </Link>
                </Reveal>
              );
            })}
          </div>
        </div>
      </section>

      {/* ---- How it works (preview) ---- */}
      <section className="border-b border-white/5 px-6 py-24">
        <div className="mx-auto max-w-6xl">
          <div className="mb-12 text-center">
            <p className="text-xs uppercase tracking-widest text-accent">
              The coordinator's day in three moves
            </p>
            <h2 className="mt-3 text-3xl font-bold sm:text-4xl">
              From the morning standup to the donor's WhatsApp — in minutes
            </h2>
          </div>

          <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
            {HOW_IT_WORKS.map((s) => {
              const Icon = s.icon;
              return (
                <div
                  key={s.n}
                  className="rounded-2xl border border-white/5 bg-surface/40 p-6"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs text-white/30">{s.n}</span>
                    <Icon className="h-5 w-5 text-accent" />
                  </div>
                  <h3 className="mt-3 text-lg font-semibold">{s.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-white/60">
                    {s.body}
                  </p>
                </div>
              );
            })}
          </div>

          <div className="mt-10 text-center">
            <Link
              href="/how-it-works"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:underline"
            >
              Read the deep dive
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </section>

      {/* ---- Trust strip ---- */}
      <section className="border-b border-white/5 px-6 py-16">
        <div className="mx-auto max-w-5xl rounded-2xl border border-white/5 bg-gradient-to-br from-primary/5 to-accent/5 p-10">
          <div className="flex flex-col items-start gap-6 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-xs uppercase tracking-widest text-accent">
                Augments, doesn't replace
              </p>
              <h3 className="mt-2 text-2xl font-semibold">
                Built around Blood Warriors' existing Blood Bridge model
              </h3>
              <p className="mt-3 max-w-2xl text-sm text-white/60">
                Plugs into eRaktKosh, ICMR's Rare Donor Registry, and Twilio
                WhatsApp. No coordinator workflow changes — the AI sits behind
                the same dashboards Blood Warriors already runs.
              </p>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center">
              <Pill icon={ShieldCheck} label="eRaktKosh" />
              <Pill icon={Droplet} label="ICMR RDRI" />
              <Pill icon={MessageSquareText} label="Twilio WA + Voice" />
              <Pill icon={Languages} label="8 languages" />
              <Pill icon={BrainCircuit} label="XGBoost + SHAP" />
              <Pill icon={CalendarClock} label="OR-Tools" />
              <Pill icon={Cloud} label="AWS ECS + RDS" />
              <Pill icon={Sparkles} label="Bedrock Claude 4.5" />
              <Pill icon={ShieldCheck} label="Cognito RBAC" />
            </div>
          </div>
        </div>
      </section>

      {/* ---- Final CTA ---- */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="text-4xl font-bold tracking-tight sm:text-5xl">
            Ready to look under the hood?
          </h2>
          <p className="mt-4 text-base text-white/60">
            Built by AlgoWarriors for the AI for Good Hackathon 2026.
            Every model, scheduler, and integration is live — no slideware.
          </p>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/bridges"
              className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-primary/30 transition-colors hover:bg-primary-600"
            >
              Open dashboard
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/simulator"
              className="inline-flex items-center gap-2 rounded-full border border-white/15 px-6 py-3 text-sm font-medium text-white/80 transition-colors hover:border-white/30 hover:text-white"
            >
              Try the live simulator
            </Link>
          </div>

          <div className="mt-8 inline-flex flex-wrap items-center justify-center gap-3 text-xs text-white/40">
            <span className="inline-flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
              887+ tests green · 673 backend · 214 frontend
            </span>
            <span className="text-white/20">·</span>
            <span className="inline-flex items-center gap-1.5">
              <Cloud className="h-3.5 w-3.5 text-sky-400" />
              Live on AWS — ECS Fargate · RDS pgvector · Cognito · Bedrock · SES · SQS · SNS · EventBridge · CloudWatch
            </span>
          </div>
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}

function Pill({
  icon: Icon,
  label,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[11px] text-white/70">
      <Icon className="h-3 w-3 text-accent" />
      {label}
    </span>
  );
}
