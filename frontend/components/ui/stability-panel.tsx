"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowDown, ArrowUp, Brain, Info } from "lucide-react";

import { ChurnBar } from "@/components/ui/churn-bar";
import { HealthBadge } from "@/components/ui/health-badge";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export function StabilityPanel({ bridgeId }: { bridgeId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["stability", bridgeId],
    queryFn: () => api.getBridgeStability(bridgeId),
    retry: false,
  });

  if (isLoading) {
    return (
      <section className="mt-8">
        <h2 className="mb-3 text-lg font-semibold text-white">Cohort Stability</h2>
        <div className="h-64 animate-pulse rounded-xl bg-surface/40" />
      </section>
    );
  }

  if (error) {
    const is503 = /503/.test(error.message) || /not loaded/i.test(error.message);
    return (
      <section className="mt-8">
        <h2 className="mb-3 text-lg font-semibold text-white">Cohort Stability</h2>
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-200/90">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" />
            {is503 ? "Stability model not trained" : "Could not load stability"}
          </div>
          <p className="mt-1 text-amber-200/70">
            {is503
              ? "Run "
              : null}
            {is503 ? (
              <code className="rounded bg-black/30 px-1">python -m scripts.train_stability</code>
            ) : null}
            {is503 ? " then restart the backend." : error.message}
          </p>
        </div>
      </section>
    );
  }

  if (!data) return null;

  const sorted = [...data.members].sort((a, b) => b.churn_90d - a.churn_90d);

  return (
    <section className="mt-8" data-testid="stability-panel">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Cohort Stability</h2>
          <p className="text-xs text-white/50">
            Predicted by XGBoost · {data.model_version} · sorted by 90-day churn risk
          </p>
        </div>
        <HealthBadge health={data.aggregate.ml_health} />
      </div>

      {/* Aggregate stats */}
      <div className="mb-4 grid grid-cols-3 gap-3">
        <AggStat
          label="Average 90d churn"
          value={`${Math.round(data.aggregate.avg_churn_90d * 100)}%`}
        />
        <AggStat
          label="Highest at-risk"
          value={`${Math.round(data.aggregate.max_churn_90d * 100)}%`}
          danger={data.aggregate.max_churn_90d >= 0.5}
        />
        <AggStat
          label="Donors ≥ 50% risk"
          value={`${data.aggregate.at_risk_donor_count} / ${data.aggregate.active_donor_count}`}
          danger={data.aggregate.at_risk_donor_count > 0}
        />
      </div>

      {/* Per-donor cards */}
      <div className="space-y-3">
        {sorted.map((m) => {
          const isHigh = m.churn_90d >= 0.5;
          return (
            <div
              key={m.donor_id}
              className={cn(
                "rounded-xl border bg-surface/30 p-4",
                isHigh
                  ? "border-red-500/40 bg-red-500/5"
                  : "border-white/5",
              )}
              data-testid="stability-donor"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium text-white">{m.donor_name}</h3>
                    {isHigh ? (
                      <span className="rounded-full bg-red-500/20 px-2 py-0.5 text-[10px] uppercase tracking-wider text-red-300">
                        At risk
                      </span>
                    ) : null}
                  </div>
                </div>
                <div className="text-right text-xs text-white/40">
                  <Brain className="ml-auto h-3.5 w-3.5" aria-hidden />
                </div>
              </div>

              {/* Churn bars */}
              <div className="mt-3 space-y-1.5">
                <ChurnBar value={m.churn_30d} label="30d" />
                <ChurnBar value={m.churn_60d} label="60d" />
                <ChurnBar value={m.churn_90d} label="90d" />
              </div>

              {/* SHAP factors */}
              {m.top_factors.length > 0 ? (
                <div className="mt-3 space-y-1">
                  <p className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-white/40">
                    <Info className="h-3 w-3" />
                    Why this score
                  </p>
                  <ul className="space-y-1">
                    {m.top_factors.map((f) => (
                      <li
                        key={f.feature}
                        className="flex items-center gap-2 text-xs text-white/70"
                      >
                        {f.direction === "increases_churn" ? (
                          <ArrowUp
                            className="h-3 w-3 shrink-0 text-red-400"
                            aria-label="Increases churn"
                          />
                        ) : (
                          <ArrowDown
                            className="h-3 w-3 shrink-0 text-emerald-400"
                            aria-label="Decreases churn"
                          />
                        )}
                        <span>{f.label}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function AggStat({
  label,
  value,
  danger = false,
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-surface/30 p-3",
        danger ? "border-red-500/30" : "border-white/5",
      )}
    >
      <p className="text-[11px] uppercase tracking-wider text-white/40">{label}</p>
      <p
        className={cn(
          "mt-1 text-lg font-semibold tabular-nums",
          danger ? "text-red-300" : "text-white",
        )}
      >
        {value}
      </p>
    </div>
  );
}
