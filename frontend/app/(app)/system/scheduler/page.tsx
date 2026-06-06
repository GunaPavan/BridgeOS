"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, RefreshCw, Sparkles } from "lucide-react";

import { DispatchQueueTile } from "@/components/ui/dispatch-queue-tile";
import { EventsFeedPanel } from "@/components/ui/events-feed-panel";
import { JobRunHistory } from "@/components/ui/job-run-history";
import { JobStatusCard } from "@/components/ui/job-status-card";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function SchedulerPage() {
  const qc = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["scheduler-status"],
    queryFn: () => api.getSchedulerStatus(),
    refetchInterval: 10_000,
  });
  const { data: health } = useQuery({
    queryKey: ["scheduler-health"],
    queryFn: () => api.getSchedulerHealth(),
    refetchInterval: 15_000,
  });

  const demo = useMutation({
    mutationFn: (enabled: boolean) => api.setSchedulerDemoMode(enabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scheduler-status"] }),
  });

  return (
    <div className="px-8 py-8" data-testid="scheduler-page">
      <header className="mb-6 flex items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Activity className="h-3.5 w-3.5" />
            Automation Engine
          </div>
          <h1 className="mt-1 text-3xl font-bold text-white">Background scheduler</h1>
          <p className="mt-1 text-sm text-white/60">
            Allocator cycles, expiry sweeps, donor follow-ups and reply handling
            — running without an operator clicking anything.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => refetch()}
            className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-white/70 hover:border-white/20 hover:text-white"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
          <button
            type="button"
            data-testid="demo-mode-toggle"
            onClick={() => demo.mutate(!data?.demo_mode)}
            disabled={demo.isPending || !data?.running}
            className={cn(
              "inline-flex items-center gap-1 rounded-lg border px-3 py-1.5 text-sm transition-colors",
              data?.demo_mode
                ? "border-red-500/40 bg-red-500/15 text-red-300 hover:bg-red-500/25"
                : "border-primary/40 bg-primary/10 text-primary hover:bg-primary/20",
            )}
          >
            <Sparkles className="h-3.5 w-3.5" />
            {data?.demo_mode ? "Exit demo mode" : "Enter demo mode"}
          </button>
        </div>
      </header>

      {/* Summary row */}
      {data && (
        <section className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="scheduler-summary">
          <Stat label="Status" value={data.running ? "running" : "stopped"} tone={data.running ? "ok" : "warn"} />
          <Stat label="Jobs" value={`${data.enabled_count} / ${data.job_count}`} hint="enabled / total" tone="default" />
          <Stat label="Failures (24h)" value={String(data.failures_24h)} tone={data.failures_24h > 0 ? "warn" : "ok"} />
          <Stat label="Demo mode" value={data.demo_mode ? "ON" : "off"} tone={data.demo_mode ? "warn" : "default"} />
        </section>
      )}

      {/* Health issues */}
      {health && health.issues.length > 0 && (
        <div className="mb-6 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          <AlertTriangle className="mt-0.5 h-4 w-4" />
          <div>
            <p className="font-medium">Scheduler health: {health.issues.length} issue(s)</p>
            <ul className="mt-1 list-disc pl-4 text-xs text-red-200/85">
              {health.issues.map((i) => (
                <li key={i}>{i}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {isLoading && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-32 animate-pulse rounded-xl border border-white/5 bg-surface/30" />
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          Could not load scheduler status. Backend should be running at
          <code className="ml-1 rounded bg-black/30 px-1">/system/scheduler/status</code>.
        </div>
      )}

      {/* Job grid */}
      {data && (
        <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="job-grid">
          {data.jobs.map((j) => (
            <JobStatusCard key={j.name} job={j} />
          ))}
        </section>
      )}

      {/* Dispatch queue */}
      <section className="mt-8" data-testid="dispatch-queue-section">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-white/40">
          Outbound dispatch
        </h2>
        <DispatchQueueTile />
      </section>

      {/* Event bus */}
      <section className="mt-8" data-testid="events-feed-section">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-white/40">
          Event bus
        </h2>
        <EventsFeedPanel />
      </section>

      {/* Recent runs */}
      <section className="mt-8" data-testid="recent-runs">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-white/40">
          Recent runs
        </h2>
        <JobRunHistory limit={50} />
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone: "ok" | "warn" | "default";
}) {
  const toneCls =
    tone === "ok"
      ? "text-emerald-300"
      : tone === "warn"
        ? "text-amber-300"
        : "text-white";
  return (
    <div className="rounded-xl border border-white/5 bg-surface/40 p-3">
      <p className="text-[10px] uppercase tracking-wider text-white/40">{label}</p>
      <p className={cn("mt-1 text-lg font-semibold tabular-nums", toneCls)}>{value}</p>
      {hint ? <p className="text-[10px] text-white/30">{hint}</p> : null}
    </div>
  );
}
