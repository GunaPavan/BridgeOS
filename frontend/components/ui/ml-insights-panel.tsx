"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  PhoneOff,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Real-data ML-driven insights for the entire donor pool — surfaced on the
 * /analytics page. Scores 500 donors through both production models and
 * shows the actionable aggregates (intervention counts, survival quartiles,
 * predicted class distribution).
 */
export function MLInsightsPanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["ml-donor-pool-insights"],
    queryFn: () => api.getDonorPoolInsights(),
    staleTime: 60_000,
    retry: false,
  });

  if (isLoading) {
    return (
      <div
        data-testid="ml-insights-panel-loading"
        className="rounded-xl border border-white/5 bg-surface/40 p-5"
      >
        <div className="h-32 animate-pulse rounded-lg bg-white/5" />
      </div>
    );
  }

  if (error || !data || data.n_scored === 0) {
    return null;
  }

  const total = Math.max(
    1,
    (data.predicted_class_counts.active ?? 0) +
      (data.predicted_class_counts.inactive_not_donated_1y ?? 0) +
      (data.predicted_class_counts.inactive_limited_despite_calls ?? 0),
  );
  const activePct =
    ((data.predicted_class_counts.active ?? 0) / total) * 100;
  const notDonatedPct =
    ((data.predicted_class_counts.inactive_not_donated_1y ?? 0) / total) * 100;
  const limitedPct =
    ((data.predicted_class_counts.inactive_limited_despite_calls ?? 0) /
      total) *
    100;

  return (
    <section
      data-testid="ml-insights-panel"
      className="rounded-xl border border-white/5 bg-surface/40 p-5"
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-white/40">
            <Activity className="h-4 w-4 text-accent" />
            ML-driven network insights
          </h2>
          <p className="mt-0.5 text-[11px] text-white/40">
            Live scoring of {data.n_scored} donors via{" "}
            <span className="font-mono text-sky-300">{data.churn_winner}</span> +{" "}
            <span className="font-mono text-violet-300">{data.survival_winner}</span>
          </p>
        </div>
      </div>

      {/* --- Predicted class distribution (stacked bar) --- */}
      <div className="mb-4" data-testid="predicted-class-bar">
        <div className="mb-1.5 flex items-center justify-between text-[10px] uppercase tracking-wider text-white/40">
          <span>Predicted engagement class</span>
          <span>{total} donors</span>
        </div>
        <div className="flex h-6 overflow-hidden rounded-md border border-white/5 bg-black/40">
          <div
            className="flex items-center justify-center bg-emerald-500/30 text-[10px] font-medium text-emerald-200"
            style={{ width: `${activePct}%` }}
            title={`Active: ${data.predicted_class_counts.active ?? 0}`}
          >
            {activePct > 15 ? `${Math.round(activePct)}%` : null}
          </div>
          <div
            className="flex items-center justify-center bg-amber-500/30 text-[10px] font-medium text-amber-200"
            style={{ width: `${notDonatedPct}%` }}
            title={`Not donated 1Y: ${data.predicted_class_counts.inactive_not_donated_1y ?? 0}`}
          >
            {notDonatedPct > 8 ? `${Math.round(notDonatedPct)}%` : null}
          </div>
          <div
            className="flex items-center justify-center bg-red-500/30 text-[10px] font-medium text-red-200"
            style={{ width: `${limitedPct}%` }}
            title={`Limited despite calls: ${data.predicted_class_counts.inactive_limited_despite_calls ?? 0}`}
          >
            {limitedPct > 8 ? `${Math.round(limitedPct)}%` : null}
          </div>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[10px] text-white/55">
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm bg-emerald-400/70" /> Active
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm bg-amber-400/70" /> Not donated 1Y
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm bg-red-400/70" /> Limited despite calls
          </span>
        </div>
      </div>

      {/* --- Action-required cards (intervention counts) --- */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <InsightCard
          testid="insight-needs-reminder"
          icon={AlertCircle}
          tone="amber"
          label="Need reminder"
          value={data.needs_reminder_count}
          hint="Send friendly nudge — likely to convert"
        />
        <InsightCard
          testid="insight-stop-calling"
          icon={PhoneOff}
          tone="red"
          label="Stop calling"
          value={data.stop_calling_count}
          hint="Call fatigue — switch channel or accept"
        />
        <InsightCard
          testid="insight-low-risk"
          icon={CheckCircle2}
          tone="emerald"
          label="Low churn risk"
          value={data.low_risk_count}
          hint="p(active) ≥ 0.70 — keep cadence"
        />
        <InsightCard
          testid="insight-high-risk"
          icon={TrendingDown}
          tone="red"
          label="High churn risk"
          value={data.high_risk_count}
          hint="p(active) < 0.30 — urgent triage"
        />
      </div>

      {/* --- Survival quartiles --- */}
      <div
        data-testid="survival-quartiles"
        className="mt-4 rounded-lg border border-violet-400/20 bg-violet-500/5 p-3"
      >
        <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-violet-200/70">
          <span className="inline-flex items-center gap-1">
            <TrendingUp className="h-3 w-3" /> 365-day survival probability
          </span>
          <span>across {data.n_scored} donors</span>
        </div>
        <div className="mt-2 grid grid-cols-3 gap-2 text-center text-xs">
          <Quartile label="p25" value={data.survival_365d_p25} tone="dim" />
          <Quartile label="median" value={data.survival_365d_median} tone="bold" />
          <Quartile label="p75" value={data.survival_365d_p75} tone="dim" />
        </div>
        <p className="mt-2 text-[11px] text-white/40">
          Mean predicted P(active) across pool:{" "}
          <span className="font-mono text-violet-200">
            {Math.round(data.p_active_mean * 100)}%
          </span>
        </p>
      </div>
    </section>
  );
}

function InsightCard({
  testid,
  icon: Icon,
  tone,
  label,
  value,
  hint,
}: {
  testid: string;
  icon: typeof AlertCircle;
  tone: "amber" | "red" | "emerald";
  label: string;
  value: number;
  hint: string;
}) {
  const tones = {
    amber: "border-amber-400/30 bg-amber-500/5 text-amber-200",
    red: "border-red-400/30 bg-red-500/5 text-red-200",
    emerald: "border-emerald-400/30 bg-emerald-500/5 text-emerald-200",
  }[tone];
  return (
    <div
      data-testid={testid}
      className={cn("rounded-lg border p-3", tones)}
    >
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider opacity-70">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold tabular-nums">{value}</div>
      <p className="text-[10px] opacity-60">{hint}</p>
    </div>
  );
}

function Quartile({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "dim" | "bold";
}) {
  return (
    <div className="rounded-md border border-violet-400/15 bg-black/20 p-2">
      <div className="text-[10px] uppercase tracking-wider text-violet-200/70">
        {label}
      </div>
      <div
        className={cn(
          "mt-0.5 font-mono tabular-nums",
          tone === "bold" ? "text-lg text-violet-200" : "text-base text-violet-200/80",
        )}
      >
        {Math.round(value * 100)}%
      </div>
    </div>
  );
}
