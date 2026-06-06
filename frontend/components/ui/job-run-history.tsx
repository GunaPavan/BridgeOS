"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, MinusCircle, XCircle } from "lucide-react";

import { api, type RunSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

function statusBadge(status: RunSummary["status"]) {
  if (status === "success")
    return { Icon: CheckCircle2, color: "text-emerald-400" };
  if (status === "failed") return { Icon: XCircle, color: "text-red-400" };
  return { Icon: MinusCircle, color: "text-white/40" };
}

function fmt(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function JobRunHistory({
  job,
  limit = 50,
}: {
  job?: string;
  limit?: number;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["scheduler-runs", job ?? "all", limit],
    queryFn: () => api.listSchedulerRuns({ job, limit }),
    refetchInterval: 5000,
  });

  if (isLoading)
    return (
      <div
        data-testid="run-history-loading"
        className="h-40 animate-pulse rounded-xl border border-white/5 bg-surface/30"
      />
    );

  const items = data?.items ?? [];
  return (
    <div
      data-testid="job-run-history"
      className="overflow-hidden rounded-xl border border-white/5 bg-surface/40"
    >
      <table className="w-full text-sm">
        <thead className="bg-black/30 text-[11px] uppercase tracking-wider text-white/40">
          <tr>
            <th className="px-3 py-2 text-left">Job</th>
            <th className="px-3 py-2 text-left">Started</th>
            <th className="px-3 py-2 text-right">Items</th>
            <th className="px-3 py-2 text-right">Duration</th>
            <th className="px-3 py-2 text-right">Status</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan={5} className="px-3 py-8 text-center text-white/40">
                No runs yet for this window.
              </td>
            </tr>
          ) : (
            items.map((r) => {
              const { Icon, color } = statusBadge(r.status);
              return (
                <tr
                  key={r.id}
                  data-testid="run-row"
                  data-status={r.status}
                  className="border-t border-white/5"
                >
                  <td className="px-3 py-2 font-mono text-xs text-white/80">{r.job_name}</td>
                  <td className="px-3 py-2 text-xs text-white/70">{fmt(r.started_at)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-white/85">
                    {r.items_processed}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-white/70">
                    {r.duration_ms != null ? `${Math.round(r.duration_ms)}ms` : "—"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 text-xs",
                        color,
                      )}
                    >
                      <Icon className="h-3 w-3" />
                      {r.status}
                    </span>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
