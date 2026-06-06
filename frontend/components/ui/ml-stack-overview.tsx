"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Brain, Database, Sparkles } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * ML Stack Overview — surfaces both production models (churn + survival)
 * trained on real Blood Warriors data, with winner + headline metrics.
 *
 * Shown on /analytics so judges + admins can verify the model performance
 * at a glance without leaving the dashboard.
 */
export function MLStackOverview() {
  const { data, isLoading } = useQuery({
    queryKey: ["ml-model-metrics"],
    queryFn: () => api.getMlModelMetrics(),
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <div
        data-testid="ml-stack-overview-loading"
        className="rounded-xl border border-white/5 bg-surface/40 p-5"
      >
        <div className="h-32 animate-pulse rounded-lg bg-white/5" />
      </div>
    );
  }

  const churn = data?.churn;
  const survival = data?.survival;

  return (
    <section
      data-testid="ml-stack-overview"
      className="rounded-xl border border-white/5 bg-surface/40 p-5"
    >
      <div className="mb-3 flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-accent" />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-white/40">
          Production ML stack
        </h2>
        <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-emerald-300">
          Real Blood Warriors data
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <ModelCard
          testid="ml-card-churn"
          icon={Brain}
          tone="sky"
          title="Multi-class Churn Classifier"
          winner={churn?.winner ?? "—"}
          loaded={churn?.loaded ?? false}
          stats={
            churn?.metrics
              ? [
                  ["AUC", (churn.metrics.binary_auc ?? 0).toFixed(3)],
                  ["Macro F1", (churn.metrics.macro_f1 ?? 0).toFixed(3)],
                  [
                    "CV F1",
                    `${(churn.metrics.cv_macro_f1_mean ?? 0).toFixed(3)} ± ${(
                      churn.metrics.cv_macro_f1_std ?? 0
                    ).toFixed(3)}`,
                  ],
                ]
              : []
          }
          features={churn?.feature_names ?? []}
        />
        <ModelCard
          testid="ml-card-survival"
          icon={Activity}
          tone="violet"
          title="Time-to-Event Survival"
          winner={survival?.winner ?? "—"}
          loaded={survival?.loaded ?? false}
          stats={
            survival?.metrics
              ? [
                  ["C-index", (survival.metrics.c_index ?? 0).toFixed(3)],
                  ["Events", String(survival.metrics.n_events ?? 0)],
                  ["Censored", String(survival.metrics.n_censored ?? 0)],
                ]
              : []
          }
          features={survival?.feature_names ?? []}
        />
      </div>

      <p className="mt-3 flex items-center gap-1.5 text-[11px] text-white/40">
        <Database className="h-3 w-3" />
        Trained on 6,949 real Blood Warriors donors (Mar 2020 – Aug 2025).
        Winner selected via Borda multi-criteria ranking across CV, test, and
        latency metrics.
      </p>
    </section>
  );
}

function ModelCard({
  testid,
  icon: Icon,
  tone,
  title,
  winner,
  loaded,
  stats,
  features,
}: {
  testid: string;
  icon: typeof Brain;
  tone: "sky" | "violet";
  title: string;
  winner: string;
  loaded: boolean;
  stats: Array<[string, string]>;
  features: string[];
}) {
  const accent = {
    sky: "text-sky-300 border-sky-400/30 bg-sky-500/5",
    violet: "text-violet-300 border-violet-400/30 bg-violet-500/5",
  }[tone];
  return (
    <div
      data-testid={testid}
      className={cn("rounded-xl border p-4", accent)}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Icon className="h-3.5 w-3.5" />
            {title}
          </div>
          <h3 className="mt-1 font-mono text-base font-semibold text-white">
            {winner}
          </h3>
        </div>
        <span
          data-testid={`${testid}-loaded-status`}
          className={cn(
            "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
            loaded
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              : "border-amber-500/40 bg-amber-500/10 text-amber-300",
          )}
        >
          {loaded ? "Loaded" : "Missing"}
        </span>
      </div>

      <dl className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
        {stats.map(([k, v]) => (
          <div
            key={k}
            className="rounded-md border border-white/5 bg-black/20 p-2"
          >
            <dt className="text-[10px] uppercase tracking-wider text-white/40">
              {k}
            </dt>
            <dd className="mt-0.5 font-mono text-sm tabular-nums text-white">
              {v}
            </dd>
          </div>
        ))}
      </dl>

      {features.length > 0 ? (
        <details className="mt-3 text-[11px] text-white/50">
          <summary className="cursor-pointer">
            {features.length} features
          </summary>
          <ul className="mt-2 flex flex-wrap gap-1">
            {features.slice(0, 12).map((f) => (
              <li
                key={f}
                className="rounded border border-white/5 bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-white/60"
              >
                {f}
              </li>
            ))}
            {features.length > 12 ? (
              <li className="text-[10px] text-white/40">
                +{features.length - 12} more
              </li>
            ) : null}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
