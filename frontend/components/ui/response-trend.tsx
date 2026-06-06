"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { api, type ResponseEvent } from "@/lib/api";
import { Sparkline } from "@/components/ui/sparkline";
import { cn } from "@/lib/utils";

const SIGNIFICANT_DELTA = 0.05;
const TREND_WINDOW_DAYS = 7;

/**
 * Donor-profile widget: sparkline of recent EMA points + 7-day change badge.
 *
 * Powered by `/donors/{id}/response-history`. The same endpoint runs the lazy
 * no-reply decay before returning, so the "current_response_rate" shown here
 * is up-to-date even if the donor went silent on an old outbound.
 */
export function ResponseTrend({
  donorId,
  days = 30,
  className,
}: {
  donorId: string;
  days?: number;
  className?: string;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["response-history", donorId, days],
    queryFn: () => api.getResponseHistory(donorId, days),
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <div
        data-testid="response-trend-loading"
        className={cn(
          "h-20 animate-pulse rounded-xl border border-white/5 bg-surface/30",
          className,
        )}
      />
    );
  }
  if (!data) return null;

  const values = data.events.map((e) => e.new_response_rate);
  const current = data.current_response_rate;
  const direction = computeDirection(data.events, current);

  return (
    <div
      data-testid="response-trend"
      data-direction={direction.kind}
      className={cn(
        "rounded-xl border border-white/5 bg-surface/40 p-4",
        className,
      )}
    >
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-white/40">
          <Activity className="h-3 w-3" />
          Response trend ({days}d)
        </div>
        <ChangeBadge direction={direction} />
      </div>

      <div className="flex items-end justify-between gap-3">
        <div>
          <p
            data-testid="response-trend-current"
            className="text-2xl font-bold tabular-nums text-white"
          >
            {Math.round(current * 100)}%
          </p>
          <p className="text-[11px] text-white/40">
            {data.events.length} event{data.events.length === 1 ? "" : "s"} logged
          </p>
        </div>
        <div className="text-primary">
          <Sparkline
            values={[...values, current]}
            width={160}
            height={42}
            stroke="currentColor"
            testid="response-trend-sparkline"
          />
        </div>
      </div>
    </div>
  );
}

interface Direction {
  kind: "up" | "down" | "flat";
  delta: number;
}

function computeDirection(events: ResponseEvent[], current: number): Direction {
  // Find the most recent event >= TREND_WINDOW_DAYS ago, use its new_response_rate
  // as the "baseline" we're comparing the current value against.
  const cutoff = Date.now() - TREND_WINDOW_DAYS * 24 * 3600 * 1000;
  const olderEvents = events.filter((e) => e.at && Date.parse(e.at) <= cutoff);
  const baseline =
    olderEvents.length > 0
      ? olderEvents[olderEvents.length - 1].new_response_rate
      : events[0]?.new_response_rate ?? current;
  const delta = current - baseline;
  if (Math.abs(delta) < SIGNIFICANT_DELTA) return { kind: "flat", delta };
  return { kind: delta > 0 ? "up" : "down", delta };
}

function ChangeBadge({ direction }: { direction: Direction }) {
  const pct = Math.round(Math.abs(direction.delta) * 100);
  const styles = {
    up: {
      cls: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
      icon: ArrowUpRight,
      label: `+${pct}% (7d)`,
    },
    down: {
      cls: "border-red-500/40 bg-red-500/10 text-red-300",
      icon: ArrowDownRight,
      label: `-${pct}% (7d)`,
    },
    flat: {
      cls: "border-white/10 bg-white/5 text-white/50",
      icon: Minus,
      label: "stable (7d)",
    },
  }[direction.kind];
  const Icon = styles.icon;
  return (
    <span
      data-testid="response-trend-badge"
      data-direction={direction.kind}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
        styles.cls,
      )}
    >
      <Icon className="h-2.5 w-2.5" />
      {styles.label}
    </span>
  );
}
