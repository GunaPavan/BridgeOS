"use client";

import { useQuery } from "@tanstack/react-query";
import { Clock } from "lucide-react";

import { api } from "@/lib/api";

/**
 * Compact dataset-anchor indicator shown in the sidebar.
 *
 * Blood Warriors' dataset is a snapshot — all time-since/time-until fields
 * are computed against the dataset's reference date, not wall-clock now.
 * This banner makes that contract visible.
 */
export function DatasetClockBanner() {
  const { data } = useQuery({
    queryKey: ["system-clock"],
    queryFn: () => api.getSystemClock(),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });

  if (!data) return null;

  const tone = data.is_anchored
    ? "border-amber-400/30 bg-amber-500/5 text-amber-200"
    : "border-emerald-400/30 bg-emerald-500/5 text-emerald-200";

  return (
    <div
      data-testid="dataset-clock-banner"
      data-anchored={data.is_anchored}
      className={`mx-3 mb-3 rounded-lg border px-3 py-2 ${tone}`}
      title={data.label}
    >
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider">
        <Clock className="h-3 w-3" />
        Data clock
      </div>
      <p className="mt-0.5 font-mono text-xs">{data.today}</p>
      {data.is_anchored ? (
        <p className="mt-0.5 text-[10px] opacity-70">
          Snapshot · {data.days_anchored_back}d behind real time
        </p>
      ) : (
        <p className="mt-0.5 text-[10px] opacity-70">Live</p>
      )}
    </div>
  );
}
