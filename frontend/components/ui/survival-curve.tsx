"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, TrendingDown } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Time-to-event survival card — surfaces predictions from the real-data
 * GradientBoostingSurvival model (C-index 0.751, 0.3 ms inference).
 *
 * Shows the donor's probability of *remaining active* at 90 / 180 / 365 days.
 * A simple polyline gives an at-a-glance survival curve plus the risk score.
 */
export function SurvivalCurve({ donorId }: { donorId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["donor-survival", donorId],
    queryFn: () => api.getDonorSurvival(donorId),
    retry: false,
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <div
        data-testid="survival-curve-loading"
        className="rounded-xl border border-white/5 bg-surface/40 p-5"
      >
        <div className="h-32 animate-pulse rounded-lg bg-white/5" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div
        data-testid="survival-curve-error"
        className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-200/90"
      >
        <div className="flex items-center gap-2 font-medium">
          <AlertTriangle className="h-4 w-4" />
          Survival prediction unavailable
        </div>
        <p className="mt-1 text-xs text-amber-200/70">
          Survival model not loaded. Run{" "}
          <code className="font-mono">python -m app.ml.survival.bakeoff</code>.
        </p>
      </div>
    );
  }

  // Build a 4-point survival curve: t=0 (S=1), 90, 180, 365.
  const points = [
    { t: 0, s: 1 },
    { t: 90, s: data.p_survive_90d },
    { t: 180, s: data.p_survive_180d },
    { t: 365, s: data.p_survive_365d },
  ];

  // Project onto an SVG 220×60 box
  const W = 220;
  const H = 60;
  const maxT = 365;
  const path = points
    .map(({ t, s }, i) => {
      const x = (t / maxT) * W;
      const y = H - s * H;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const lowestProb = Math.min(
    data.p_survive_90d,
    data.p_survive_180d,
    data.p_survive_365d,
  );
  const tone =
    lowestProb >= 0.85
      ? "emerald"
      : lowestProb >= 0.65
      ? "amber"
      : "red";
  const accent = {
    emerald: "text-emerald-300",
    amber: "text-amber-300",
    red: "text-red-300",
  }[tone];
  const stroke = {
    emerald: "stroke-emerald-400",
    amber: "stroke-amber-400",
    red: "stroke-red-400",
  }[tone];

  return (
    <section
      data-testid="survival-curve"
      data-tone={tone}
      className="rounded-xl border border-white/5 bg-surface/40 p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Activity className="h-3.5 w-3.5" />
            Survival curve
          </div>
          <h3 className={cn("mt-1 text-lg font-semibold", accent)}>
            <span className="inline-flex items-center gap-2">
              <TrendingDown className="h-4 w-4" />
              Risk score {data.risk_score.toFixed(2)}
            </span>
          </h3>
        </div>
        <span
          data-testid="survival-model-tag"
          title={`Winner: ${data.model_winner}\nC-index: ${(data.model_metrics.c_index ?? 0).toFixed(3)}`}
          className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider text-white/50"
        >
          {data.model_winner}
        </span>
      </div>

      {/* SVG curve */}
      <div className="mt-4 rounded-lg border border-white/5 bg-black/30 p-3">
        <svg
          data-testid="survival-curve-svg"
          viewBox={`0 0 ${W} ${H + 14}`}
          className="w-full"
          role="img"
          aria-label="Donor survival probability over time"
        >
          {/* gridlines at 0.25, 0.5, 0.75 */}
          {[0.25, 0.5, 0.75].map((y) => (
            <line
              key={y}
              x1={0}
              x2={W}
              y1={H - y * H}
              y2={H - y * H}
              className="stroke-white/5"
              strokeDasharray="2 2"
            />
          ))}
          {/* survival path */}
          <path
            d={path}
            className={cn("fill-none stroke-2", stroke)}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {/* endpoints */}
          {points.map(({ t, s }, i) => (
            <circle
              key={i}
              cx={(t / maxT) * W}
              cy={H - s * H}
              r={2.5}
              className={cn("fill-white/90", stroke.replace("stroke-", ""))}
            />
          ))}
          {/* axis labels */}
          <text x={0} y={H + 12} className="fill-white/40 text-[8px]">
            0d
          </text>
          <text x={W * (90 / maxT) - 4} y={H + 12} className="fill-white/40 text-[8px]">
            90
          </text>
          <text x={W * (180 / maxT) - 6} y={H + 12} className="fill-white/40 text-[8px]">
            180
          </text>
          <text x={W - 22} y={H + 12} className="fill-white/40 text-[8px]">
            365
          </text>
        </svg>
      </div>

      {/* Probability table */}
      <dl className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
        <div data-testid="survival-90d" className="rounded-md border border-white/5 bg-white/5 p-2">
          <dt className="text-[10px] uppercase tracking-wider text-white/40">
            90 days
          </dt>
          <dd className={cn("mt-0.5 font-mono text-base tabular-nums", accent)}>
            {Math.round(data.p_survive_90d * 100)}%
          </dd>
        </div>
        <div data-testid="survival-180d" className="rounded-md border border-white/5 bg-white/5 p-2">
          <dt className="text-[10px] uppercase tracking-wider text-white/40">
            180 days
          </dt>
          <dd className={cn("mt-0.5 font-mono text-base tabular-nums", accent)}>
            {Math.round(data.p_survive_180d * 100)}%
          </dd>
        </div>
        <div data-testid="survival-365d" className="rounded-md border border-white/5 bg-white/5 p-2">
          <dt className="text-[10px] uppercase tracking-wider text-white/40">
            365 days
          </dt>
          <dd className={cn("mt-0.5 font-mono text-base tabular-nums", accent)}>
            {Math.round(data.p_survive_365d * 100)}%
          </dd>
        </div>
      </dl>

      {data.median_survival_days !== null ? (
        <p className="mt-2 text-[11px] text-white/40">
          Median time to disengagement: {data.median_survival_days.toFixed(0)} days
        </p>
      ) : null}
    </section>
  );
}
