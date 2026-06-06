"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Brain,
  CheckCircle2,
  Inbox,
  LayoutDashboard,
  Network,
  PhoneOff,
  Play,
  Sparkles,
  TrendingUp,
  UserCircle2,
  Users,
} from "lucide-react";

import { AnimatedCounter } from "@/components/ui/animated-counter";
import { SchedulerTick } from "@/components/ui/scheduler-tick";
import { StatTile } from "@/components/ui/stat-tile";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const URGENCY_PILL = {
  critical: "border-red-500/40 bg-red-500/15 text-red-300",
  high: "border-amber-500/40 bg-amber-500/15 text-amber-300",
  medium: "border-blue-500/40 bg-blue-500/15 text-blue-300",
} as const;

export default function OverviewPage() {
  const analyticsQ = useQuery({
    queryKey: ["analytics"],
    queryFn: () => api.getAnalytics(),
    staleTime: 60_000,
  });
  const recsQ = useQuery({
    queryKey: ["recommendations", { top_k: 5 }],
    queryFn: () =>
      api.listRecommendations({ onlyWeak: true, topKPerBridge: 5 }),
    staleTime: 60_000,
  });
  const insightsQ = useQuery({
    queryKey: ["ml-donor-pool-insights"],
    queryFn: () => api.getDonorPoolInsights(),
    staleTime: 60_000,
    retry: false,
  });
  const clockQ = useQuery({
    queryKey: ["system-clock"],
    queryFn: () => api.getSystemClock(),
    staleTime: 5 * 60 * 1000,
  });

  const analytics = analyticsQ.data;
  const recs = recsQ.data?.items ?? [];
  const insights = insightsQ.data;

  const criticalCount = recs.filter((r) => r.urgency === "critical").length;
  const highCount = recs.filter((r) => r.urgency === "high").length;
  const topRecs = recs.slice(0, 5);
  const totalWeakDonors = recs.reduce(
    (sum, r) => sum + r.weak_donors.length,
    0,
  );

  return (
    <div className="px-8 py-8" data-testid="overview-page">
      {/* --- Header --- */}
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <LayoutDashboard className="h-3.5 w-3.5" />
            Overview
          </div>
          <h1 className="mt-1 text-3xl font-bold text-white">
            Today on Bridge OS
          </h1>
          <p className="mt-1 text-sm text-white/60">
            {clockQ.data ? (
              clockQ.data.is_anchored ? (
                <>
                  Reference date{" "}
                  <span className="font-mono text-amber-200">
                    {clockQ.data.today}
                  </span>{" "}
                  · dataset snapshot ({clockQ.data.days_anchored_back}d behind real time)
                </>
              ) : (
                <>
                  Live as of{" "}
                  <span className="font-mono text-emerald-200">
                    {clockQ.data.today}
                  </span>
                </>
              )
            ) : (
              "Loading data clock…"
            )}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <SchedulerTick job="auto_run_cycle" />
          {recsQ.isLoading || analyticsQ.isLoading ? (
            <span className="text-xs text-white/40">Loading…</span>
          ) : (
            <span className="text-xs text-emerald-300/80">
              <CheckCircle2 className="-mt-0.5 mr-1 inline h-3 w-3" />
              All systems live
            </span>
          )}
        </div>
      </header>

      {/* --- KPI row --- */}
      <section
        className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
        data-testid="overview-kpis"
      >
        <StatTile
          icon={UserCircle2}
          label="Patients in care"
          value={
            analytics ? (
              <AnimatedCounter value={analytics.total_patients} />
            ) : (
              "—"
            )
          }
          tone="primary"
        />
        <StatTile
          icon={Users}
          label="Active donors"
          value={
            analytics ? (
              <AnimatedCounter value={analytics.donor_pool.active} />
            ) : (
              "—"
            )
          }
          hint={analytics ? `of ${analytics.total_donors} pool` : undefined}
          tone="accent"
        />
        <StatTile
          icon={Network}
          label="Active bridges"
          value={
            analytics ? (
              <AnimatedCounter value={analytics.cohort_stats.total_bridges} />
            ) : (
              "—"
            )
          }
          hint={
            analytics
              ? `avg ${analytics.cohort_stats.avg_active_donors.toFixed(1)} donors`
              : undefined
          }
        />
        <StatTile
          icon={AlertTriangle}
          label="Critical bridges"
          value={<AnimatedCounter value={criticalCount} />}
          hint={`${highCount} high-urgency`}
          tone={criticalCount > 0 ? "danger" : undefined}
        />
        <StatTile
          icon={Inbox}
          label="Need reminder"
          value={
            insights ? (
              <AnimatedCounter value={insights.needs_reminder_count} />
            ) : (
              "—"
            )
          }
          hint="Predicted: not donated 1Y"
        />
        <StatTile
          icon={PhoneOff}
          label="Stop calling"
          value={
            insights ? (
              <AnimatedCounter value={insights.stop_calling_count} />
            ) : (
              "—"
            )
          }
          hint="Predicted: limited despite calls"
          tone={
            insights && insights.stop_calling_count > 0 ? "danger" : undefined
          }
        />
      </section>

      {/* --- Main grid: attention + ML quick view --- */}
      <section className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Left: needs attention */}
        <div
          className="rounded-xl border border-white/5 bg-surface/40 p-5 lg:col-span-2"
          data-testid="needs-attention-panel"
        >
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-white/40">
                <AlertTriangle className="h-4 w-4 text-red-400/80" />
                Needs attention today
              </h2>
              <p className="mt-0.5 text-[11px] text-white/40">
                Top {Math.min(topRecs.length, 5)} bridges by ML churn risk · {totalWeakDonors} at-risk donors total
              </p>
            </div>
            <Link
              href="/recommendations"
              className="inline-flex items-center gap-1 text-xs text-white/60 hover:text-white"
            >
              All recommendations <ArrowRight className="h-3 w-3" />
            </Link>
          </div>

          {recsQ.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className="h-14 animate-pulse rounded-lg bg-white/5"
                />
              ))}
            </div>
          ) : topRecs.length === 0 ? (
            <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4 text-sm text-emerald-300/80">
              <CheckCircle2 className="mr-1 inline h-4 w-4" />
              Nothing on fire — every bridge is stable.
            </div>
          ) : (
            <ul className="space-y-2" data-testid="attention-list">
              {topRecs.map((r) => (
                <li key={r.bridge_id}>
                  <Link
                    href={`/bridges/${r.bridge_id}`}
                    data-testid="attention-row"
                    data-urgency={r.urgency}
                    className="block rounded-lg border border-white/5 bg-black/20 p-3 transition hover:border-white/15 hover:bg-black/30"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 text-xs text-white/40">
                          <Network className="h-3 w-3" />
                          {r.bridge_name}
                        </div>
                        <p className="mt-0.5 truncate text-sm font-medium text-white">
                          {r.patient_name}
                        </p>
                        <p className="mt-0.5 text-xs text-white/50">
                          <span className="font-mono">
                            {r.patient_blood_group}
                          </span>{" "}
                          · {r.patient_age} yrs · {r.patient_city}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <span
                          className={cn(
                            "inline-flex rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
                            URGENCY_PILL[r.urgency],
                          )}
                        >
                          {r.urgency}
                        </span>
                        <p className="mt-1 text-[11px] text-white/60">
                          {r.weak_donors.length} at-risk · {r.candidates.length} candidates
                        </p>
                      </div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Right: ML quick view */}
        <div
          className="rounded-xl border border-white/5 bg-surface/40 p-5"
          data-testid="ml-quick-view"
        >
          <div className="mb-3">
            <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-white/40">
              <Brain className="h-4 w-4 text-accent" />
              Network health
            </h2>
            <p className="mt-0.5 text-[11px] text-white/40">
              {insights
                ? `${insights.n_scored} donors scored live`
                : "Loading model output…"}
            </p>
          </div>

          {insights ? (
            <div className="space-y-4">
              <EngagementMixBar insights={insights} />
              <SurvivalMini insights={insights} />
              <Link
                href="/analytics"
                className="inline-flex items-center gap-1 text-xs text-white/60 hover:text-white"
              >
                Full analytics <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          ) : (
            <div className="h-32 animate-pulse rounded-lg bg-white/5" />
          )}
        </div>
      </section>

      {/* --- Quick actions --- */}
      <section
        className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4"
        data-testid="quick-actions"
      >
        <QuickAction
          href="/recommendations"
          icon={Inbox}
          title="Recommendations"
          subtitle={`${recs.length} bridges flagged`}
        />
        <QuickAction
          href="/simulator"
          icon={Play}
          title="Cohort simulator"
          subtitle="What if a donor exits?"
        />
        <QuickAction
          href="/analytics"
          icon={BarChart3}
          title="Analytics"
          subtitle="ML model performance"
        />
        <QuickAction
          href="/agent"
          icon={Sparkles}
          title="Care Agent"
          subtitle="Ask in 8 languages"
        />
      </section>
    </div>
  );
}

// ----- helpers -----

function EngagementMixBar({
  insights,
}: {
  insights: ReturnType<typeof api.getDonorPoolInsights> extends Promise<infer T>
    ? T
    : never;
}) {
  const counts = insights.predicted_class_counts;
  const active = counts.active ?? 0;
  const notDonated = counts.inactive_not_donated_1y ?? 0;
  const limited = counts.inactive_limited_despite_calls ?? 0;
  const total = Math.max(1, active + notDonated + limited);
  return (
    <div data-testid="engagement-mix">
      <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-white/40">
        <span>Predicted engagement</span>
        <span>{total} scored</span>
      </div>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-black/40">
        <div
          className="bg-emerald-500/70"
          style={{ width: `${(active / total) * 100}%` }}
        />
        <div
          className="bg-amber-500/70"
          style={{ width: `${(notDonated / total) * 100}%` }}
        />
        <div
          className="bg-red-500/70"
          style={{ width: `${(limited / total) * 100}%` }}
        />
      </div>
      <div className="mt-1.5 grid grid-cols-3 gap-2 text-[10px] text-white/55">
        <div>
          <p className="font-mono text-emerald-300">{active}</p>
          <p>Active</p>
        </div>
        <div>
          <p className="font-mono text-amber-300">{notDonated}</p>
          <p>Not 1Y</p>
        </div>
        <div>
          <p className="font-mono text-red-300">{limited}</p>
          <p>Limited</p>
        </div>
      </div>
    </div>
  );
}

function SurvivalMini({
  insights,
}: {
  insights: ReturnType<typeof api.getDonorPoolInsights> extends Promise<infer T>
    ? T
    : never;
}) {
  return (
    <div
      data-testid="survival-mini"
      className="rounded-lg border border-violet-400/20 bg-violet-500/5 p-3"
    >
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-violet-200/70">
        <TrendingUp className="h-3 w-3" />
        365-day survival (median)
      </div>
      <p className="mt-1 font-mono text-2xl font-semibold text-violet-200">
        {Math.round(insights.survival_365d_median * 100)}%
      </p>
      <p className="text-[10px] text-white/40">
        p(active) mean across pool:{" "}
        <span className="font-mono text-violet-200">
          {Math.round(insights.p_active_mean * 100)}%
        </span>
      </p>
    </div>
  );
}

function QuickAction({
  href,
  icon: Icon,
  title,
  subtitle,
}: {
  href: string;
  icon: typeof Activity;
  title: string;
  subtitle: string;
}) {
  return (
    <Link
      href={href}
      data-testid="quick-action"
      className="group flex items-center gap-3 rounded-xl border border-white/5 bg-surface/40 p-4 transition hover:border-primary/30 hover:bg-surface/60"
    >
      <div className="rounded-lg bg-white/5 p-2 transition group-hover:bg-primary/15">
        <Icon className="h-5 w-5 text-white/70 group-hover:text-primary" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-white">{title}</p>
        <p className="truncate text-[11px] text-white/40">{subtitle}</p>
      </div>
      <ArrowRight className="h-3.5 w-3.5 text-white/30 transition group-hover:text-primary" />
    </Link>
  );
}
