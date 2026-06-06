"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpFromLine, GitBranch, Loader2, MailX, Server } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * SQS Dispatch Queue tile — embedded on /system/scheduler.
 *
 * Shows:
 *   - Worker running indicator
 *   - Primary depth + in-flight + DLQ counters
 *   - Mode (live / mock)
 *   - Sent / failed / duplicates dropped stats
 *   - "Replay DLQ" button
 */
export function DispatchQueueTile() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["dispatch-queue-status"],
    queryFn: () => api.getDispatchQueueStatus(),
    refetchInterval: 5_000,
  });

  const replay = useMutation({
    mutationFn: () => api.replayDispatchDLQ(),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["dispatch-queue-status"] }),
  });

  if (isLoading || !data) {
    return (
      <div
        data-testid="dispatch-queue-tile-loading"
        className="h-32 animate-pulse rounded-xl border border-white/5 bg-surface/30"
      />
    );
  }

  return (
    <div
      data-testid="dispatch-queue-tile"
      className="rounded-xl border border-white/5 bg-surface/40 p-4"
    >
      <header className="mb-3 flex items-end justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-white/40">
            <Server className="h-4 w-4 text-accent" />
            Dispatch queue (SQS)
          </h3>
          <p className="mt-0.5 text-[11px] text-white/40">
            Outbound buffer between the allocator and Twilio / SES — mode:{" "}
            <span
              className={cn(
                "font-semibold",
                data.mode === "live" ? "text-emerald-300" : "text-amber-300",
              )}
            >
              {data.mode}
            </span>
          </p>
        </div>
        <button
          type="button"
          data-testid="replay-dlq-button"
          onClick={() => replay.mutate()}
          disabled={replay.isPending || data.dlq_depth === 0}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs transition-colors",
            data.dlq_depth > 0
              ? "border-amber-500/40 bg-amber-500/15 text-amber-200 hover:bg-amber-500/25"
              : "border-white/10 text-white/40 cursor-not-allowed",
          )}
        >
          {replay.isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <ArrowUpFromLine className="h-3 w-3" />
          )}
          Replay DLQ
        </button>
      </header>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Cell label="Primary depth" value={data.primary_depth} icon={Server} />
        <Cell label="In-flight" value={data.in_flight} icon={GitBranch} />
        <Cell label="DLQ depth" value={data.dlq_depth} icon={MailX} tone={data.dlq_depth > 0 ? "warn" : undefined} />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-white/60 sm:grid-cols-4">
        <Stat label="Worker">
          {data.worker_running ? (
            <span className="text-emerald-300">running</span>
          ) : (
            <span className="text-red-300">stopped</span>
          )}
        </Stat>
        <Stat label="Sent">{data.worker_sent}</Stat>
        <Stat label="Dupes dropped">{data.worker_duplicates_skipped}</Stat>
        <Stat label="Failed">{data.worker_failed}</Stat>
      </div>

      {data.error ? (
        <p className="mt-2 text-[10px] text-red-300/80">SQS error: {data.error}</p>
      ) : null}
    </div>
  );
}

function Cell({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  icon: typeof Server;
  tone?: "warn";
}) {
  return (
    <div
      data-testid={`dq-cell-${label.replace(/\s+/g, "-").toLowerCase()}`}
      className={cn(
        "rounded-md border p-2",
        tone === "warn"
          ? "border-amber-500/30 bg-amber-500/5 text-amber-200"
          : "border-white/5 bg-black/15 text-white",
      )}
    >
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider opacity-80">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <p className="mt-0.5 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded border border-white/5 bg-black/15 px-2 py-1">
      <p className="text-[9px] uppercase tracking-wider text-white/40">{label}</p>
      <p className="font-mono text-xs tabular-nums">{children}</p>
    </div>
  );
}
