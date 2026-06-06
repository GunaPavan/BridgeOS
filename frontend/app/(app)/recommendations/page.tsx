"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Brain, Inbox, RefreshCw, Trophy } from "lucide-react";

import { RecommendationCard } from "@/components/ui/recommendation-card";
import { api } from "@/lib/api";

export default function RecommendationsPage() {
  const AT_RISK_THRESHOLD = 0.65;
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["recommendations", { atRiskThreshold: AT_RISK_THRESHOLD }],
    queryFn: () =>
      api.listRecommendations({
        onlyWeak: true,
        topKPerBridge: 4,
        atRiskThreshold: AT_RISK_THRESHOLD,
      }),
  });

  // Surface the ML model that's actually scoring weak donors + candidates.
  const { data: mlMetrics } = useQuery({
    queryKey: ["ml-metrics"],
    queryFn: () => api.getMlModelMetrics(),
    staleTime: 60_000,
  });

  return (
    <div className="px-8 py-8">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Inbox className="h-3.5 w-3.5" />
            Recommendations
          </div>
          <h1 className="mt-1 text-3xl font-bold text-white">
            Recruitment Inbox
          </h1>
          <p className="mt-1 text-sm text-white/60">
            {data
              ? `${data.total} bridge${data.total === 1 ? "" : "s"} with at-risk donors. Real-data ML in the loop.`
              : "Computing recommendations…"}
          </p>
          {mlMetrics?.churn?.loaded && mlMetrics.churn.winner ? (
            <div
              data-testid="recommendations-ml-pill"
              className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-sky-400/30 bg-sky-500/10 px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-sky-200"
              title={`Multi-class churn classifier (${mlMetrics.churn.winner}) ranking weak donors + replacement candidates`}
            >
              <Brain className="h-3 w-3" />
              <span>Powered by</span>
              <span className="font-mono">{mlMetrics.churn.winner}</span>
              {typeof mlMetrics.churn.metrics?.binary_auc === "number" ? (
                <>
                  <span className="text-sky-200/60">·</span>
                  <Trophy className="h-3 w-3" />
                  <span className="tabular-nums">
                    AUC {mlMetrics.churn.metrics.binary_auc.toFixed(3)}
                  </span>
                </>
              ) : null}
            </div>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-white/70 hover:border-white/20 hover:text-white disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </header>

      {isLoading ? <InboxSkeleton /> : null}

      {error ? (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" />
            Could not load recommendations.
          </div>
          <p className="mt-1 text-red-300/80">{error.message}</p>
        </div>
      ) : null}

      {data && data.items.length === 0 ? (
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-12 text-center text-sm text-emerald-200/80">
          <p className="text-base font-semibold">Inbox zero.</p>
          <p className="mt-1">No bridges currently have at-risk donors.</p>
        </div>
      ) : null}

      {data && data.items.length > 0 ? (
        <div className="space-y-4">
          {data.items.map((rec) => (
            <RecommendationCard
              key={rec.bridge_id}
              rec={rec}
              onRecruited={() => refetch()}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function InboxSkeleton() {
  return (
    <div className="space-y-4">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="h-64 animate-pulse rounded-xl border border-white/5 bg-surface/30"
        />
      ))}
    </div>
  );
}
