"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";

import { api } from "@/lib/api";

/**
 * Small live-tick badge for embedding on /outreach + /dashboard.
 * Shows "Allocator: next run in 2m 14s" with a 1Hz countdown.
 */
export function SchedulerTick({ job = "auto_run_cycle" }: { job?: string }) {
  const { data } = useQuery({
    queryKey: ["scheduler-status"],
    queryFn: () => api.getSchedulerStatus(),
    refetchInterval: 10_000,
  });
  const [, force] = useState(0);
  useEffect(() => {
    const t = setInterval(() => force((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  if (!data || !data.running) {
    return null;
  }
  const target = data.jobs.find((j) => j.name === job);
  if (!target) return null;

  const nextRun = target.next_run_at ? new Date(target.next_run_at).getTime() : null;
  const now = Date.now();
  const remainingSec = nextRun ? Math.max(0, Math.round((nextRun - now) / 1000)) : null;

  return (
    <div
      data-testid="scheduler-tick"
      className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-300"
      title={`Allocator next: ${target.next_run_at}`}
    >
      <Activity className="h-3 w-3 animate-pulse" />
      <span>
        Allocator{" "}
        {target.enabled ? (
          remainingSec != null ? (
            <>
              ticks in{" "}
              <span className="font-mono">
                {Math.floor(remainingSec / 60)}m {remainingSec % 60}s
              </span>
            </>
          ) : (
            "(waiting…)"
          )
        ) : (
          "(paused)"
        )}
      </span>
    </div>
  );
}
