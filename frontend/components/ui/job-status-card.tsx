"use client";

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Pause, Play, Zap } from "lucide-react";

import { api, type JobState } from "@/lib/api";
import { cn } from "@/lib/utils";

const JOB_LABELS: Record<string, string> = {
  auto_run_cycle: "Allocator cycle",
  auto_expire_and_escalate: "Expire + escalate",
  auto_pending_nudge: "Pending-ping nudge",
  auto_pre_donation_reminder: "Pre-donation reminder",
  auto_post_donation_thank_you: "Post-donation thank you",
};

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const t = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.round((now - t) / 1000);
  if (diff < 0) {
    const f = Math.abs(diff);
    if (f < 60) return `in ${f}s`;
    if (f < 3600) return `in ${Math.round(f / 60)}m`;
    return `in ${Math.round(f / 3600)}h`;
  }
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

export function JobStatusCard({ job }: { job: JobState }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [justRan, setJustRan] = useState(false);

  // 1Hz force-render so "Last run Xs ago" / "Next run Ys" tick visibly between
  // the parent's 10s status refetch. Without this, the countdown only updates
  // when the query refetches, which feels frozen.
  const [, force] = useState(0);
  useEffect(() => {
    const t = setInterval(() => force((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const pause = useMutation({
    mutationFn: () => api.pauseSchedulerJob(job.name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scheduler-status"] }),
  });
  const resume = useMutation({
    mutationFn: () => api.resumeSchedulerJob(job.name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scheduler-status"] }),
  });
  const trigger = useMutation({
    mutationFn: () => api.triggerSchedulerJob(job.name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scheduler-status"] });
      qc.invalidateQueries({ queryKey: ["scheduler-runs", "all"] });
      // Flash a "✓ Ran" confirmation for 2 seconds so the user sees feedback
      // even on jobs that complete in <100ms.
      setJustRan(true);
      window.setTimeout(() => setJustRan(false), 2000);
    },
  });

  const label = JOB_LABELS[job.name] ?? job.name;
  const togglePause = async () => {
    setBusy(true);
    try {
      if (job.enabled) {
        await pause.mutateAsync();
      } else {
        await resume.mutateAsync();
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      data-testid="job-status-card"
      data-job-name={job.name}
      data-enabled={job.enabled}
      className={cn(
        "rounded-xl border bg-surface/40 p-4 transition-colors",
        job.enabled ? "border-white/10" : "border-amber-500/30 bg-amber-500/5",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-white truncate">{label}</h3>
          <p className="mt-0.5 text-[11px] text-white/45 leading-snug">{job.description}</p>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider",
            job.enabled
              ? "bg-emerald-500/15 text-emerald-300"
              : "bg-amber-500/15 text-amber-300",
          )}
        >
          {job.enabled ? "Active" : "Paused"}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
        <div>
          <p className="text-white/40">Last run</p>
          <p className="font-mono text-white/85" data-testid="last-run">
            {relativeTime(job.last_run_at)}
          </p>
        </div>
        <div>
          <p className="text-white/40">Next run</p>
          <p className="font-mono text-white/85" data-testid="next-run">
            {relativeTime(job.next_run_at)}
          </p>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between gap-2 text-[11px] text-white/40">
        <code className="rounded bg-black/30 px-1.5 py-0.5 font-mono">
          {job.effective_cron}
        </code>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={togglePause}
            disabled={busy}
            data-testid="pause-toggle"
            className="inline-flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-white/70 hover:border-white/20 hover:text-white disabled:opacity-50"
          >
            {job.enabled ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            {job.enabled ? "Pause" : "Resume"}
          </button>
          <button
            type="button"
            onClick={() => trigger.mutate()}
            disabled={trigger.isPending}
            data-testid="trigger-now"
            data-state={
              trigger.isPending ? "running" : justRan ? "done" : "idle"
            }
            className={cn(
              "inline-flex items-center gap-1 rounded-md border px-2 py-1 transition-colors",
              trigger.isPending
                ? "border-amber-400/60 bg-amber-500/15 text-amber-200"
                : justRan
                  ? "border-emerald-400/60 bg-emerald-500/15 text-emerald-200"
                  : "border-primary/40 bg-primary/10 text-primary hover:bg-primary/20",
              "disabled:cursor-wait",
            )}
          >
            {trigger.isPending ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin" />
                Running…
              </>
            ) : justRan ? (
              <>
                <Zap className="h-3 w-3" />
                Ran ✓
              </>
            ) : (
              <>
                <Zap className="h-3 w-3" />
                Run now
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
