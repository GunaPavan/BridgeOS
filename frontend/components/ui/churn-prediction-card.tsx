"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Brain, CheckCircle2, PhoneOff } from "lucide-react";

import { api, type ChurnClass, type ChurnPrediction } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Multi-class churn classifier card — surfaces predictions from the real-data
 * XGBoost model trained on 2,622 labeled Blood Warriors donors.
 *
 *   p_active                       — donor will remain engaged
 *   p_not_donated_1y               — forgot but reachable (send reminder)
 *   p_limited_despite_calls        — call fatigue (stop outreach)
 *
 * Each class carries a recommended intervention so coordinators see what to
 * DO, not just a risk number.
 */

const CLASS_STYLE: Record<
  ChurnClass,
  {
    label: string;
    Icon: typeof CheckCircle2;
    accent: string;
    bg: string;
    border: string;
  }
> = {
  active: {
    label: "Active",
    Icon: CheckCircle2,
    accent: "text-emerald-300",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
  },
  inactive_not_donated_1y: {
    label: "Not donated 1+ year",
    Icon: AlertTriangle,
    accent: "text-amber-300",
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
  },
  inactive_limited_despite_calls: {
    label: "Limited despite calls",
    Icon: PhoneOff,
    accent: "text-red-300",
    bg: "bg-red-500/10",
    border: "border-red-500/30",
  },
};

export function ChurnPredictionCard({ donorId }: { donorId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["donor-churn", donorId],
    queryFn: () => api.getChurnPrediction(donorId),
    retry: false,
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <div
        data-testid="churn-prediction-card-loading"
        className="rounded-xl border border-white/5 bg-surface/40 p-5"
      >
        <div className="h-32 animate-pulse rounded-lg bg-white/5" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div
        data-testid="churn-prediction-card-error"
        className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-200/90"
      >
        <div className="flex items-center gap-2 font-medium">
          <AlertTriangle className="h-4 w-4" />
          Churn prediction unavailable
        </div>
        <p className="mt-1 text-xs text-amber-200/70">
          The churn model isn&apos;t loaded. Train with{" "}
          <code className="font-mono">python -m app.ml.churn.bakeoff</code>.
        </p>
      </div>
    );
  }

  const style = CLASS_STYLE[data.predicted_class];
  const Icon = style.Icon;

  return (
    <section
      data-testid="churn-prediction-card"
      data-class={data.predicted_class}
      className={cn(
        "rounded-xl border bg-surface/40 p-5",
        style.border,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Brain className="h-3.5 w-3.5" />
            Churn classifier
          </div>
          <h3 className={cn("mt-1 text-lg font-semibold", style.accent)}>
            <span className="inline-flex items-center gap-2">
              <Icon className="h-4 w-4" />
              {style.label}
            </span>
          </h3>
        </div>
        <span
          data-testid="churn-model-tag"
          title={`Winner: ${data.model_winner}\nAUC: ${(
            data.model_metrics.binary_auc ?? 0
          ).toFixed(3)}\nMacro F1: ${(data.model_metrics.macro_f1 ?? 0).toFixed(3)}`}
          className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider text-white/50"
        >
          {data.model_winner}
        </span>
      </div>

      {/* Probability bars */}
      <div className="mt-4 space-y-2" data-testid="churn-prob-bars">
        <ProbBar
          label="Active"
          value={data.p_active}
          tone="emerald"
          testid="prob-active"
        />
        <ProbBar
          label="Not donated 1Y"
          value={data.p_not_donated_1y}
          tone="amber"
          testid="prob-not-donated-1y"
        />
        <ProbBar
          label="Limited despite calls"
          value={data.p_limited_despite_calls}
          tone="red"
          testid="prob-limited"
        />
      </div>

      {/* Recommended action */}
      <div
        data-testid="churn-recommendation"
        className={cn("mt-4 rounded-lg p-3 text-sm", style.bg, style.border, "border")}
      >
        <div className="text-[10px] uppercase tracking-wider text-white/40">
          Recommended action
        </div>
        <p className={cn("mt-1 font-medium", style.accent)}>
          {data.recommended_action}
        </p>
      </div>

      {/* Top factors */}
      {data.top_factors.length > 0 ? (
        <div className="mt-4">
          <div className="text-[10px] uppercase tracking-wider text-white/40">
            Top factors driving this prediction
          </div>
          <ul className="mt-2 space-y-1.5" data-testid="churn-top-factors">
            {data.top_factors.map((f) => (
              <li
                key={f.feature}
                className="flex items-center justify-between gap-3 text-xs text-white/70"
              >
                <span className="font-mono text-white/50">{f.feature}</span>
                <span className="tabular-nums text-white/40">
                  importance {f.global_importance.toFixed(2)} · value{" "}
                  {f.value.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function ProbBar({
  label,
  value,
  tone,
  testid,
}: {
  label: string;
  value: number;
  tone: "emerald" | "amber" | "red";
  testid: string;
}) {
  const pct = Math.round(value * 100);
  const toneCls = {
    emerald: "bg-emerald-400/70",
    amber: "bg-amber-400/70",
    red: "bg-red-400/70",
  }[tone];
  return (
    <div data-testid={testid} className="flex items-center gap-2 text-xs">
      <span className="w-36 shrink-0 text-white/60">{label}</span>
      <div className="relative h-2 flex-1 rounded-full bg-white/5">
        <div
          className={cn("h-full rounded-full", toneCls)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-10 shrink-0 text-right tabular-nums text-white">
        {pct}%
      </span>
    </div>
  );
}
