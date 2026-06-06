"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  Clock,
  Loader2,
  TrendingDown,
  TrendingUp,
  XCircle,
} from "lucide-react";

import { api, type ScheduleResolveEvent } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";

/**
 * Bridge detail page panel — last 5 auto-resolve events triggered by cohort
 * changes (G1 webhook YES, manual recruit, future swap-accept, etc.). Polls
 * every 6s so the coordinator sees the re-solve flash in shortly after a
 * donor's YES lands.
 */
export function ScheduleHistoryPanel({ bridgeId }: { bridgeId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["schedule-history", bridgeId],
    queryFn: () => api.getScheduleHistory(bridgeId, 5),
    refetchInterval: 6000,
    staleTime: 4000,
  });

  if (isLoading) {
    return (
      <div
        data-testid="schedule-history-loading"
        className="h-20 animate-pulse rounded-xl border border-white/5 bg-surface/30"
      />
    );
  }
  if (!data || data.events.length === 0) return null;

  return (
    <section
      data-testid="schedule-history-panel"
      className="rounded-xl border border-white/5 bg-surface/40 p-4"
    >
      <div className="mb-3 flex items-center gap-2">
        <CalendarClock className="h-4 w-4 text-accent" />
        <h2 className="text-sm font-semibold text-white">Schedule changes</h2>
        <span className="text-[10px] uppercase tracking-wider text-white/40">
          last {data.events.length}
        </span>
      </div>
      <ul className="space-y-2">
        {data.events.map((e) => (
          <ScheduleEventRow key={e.id} event={e} />
        ))}
      </ul>
    </section>
  );
}

interface DeltaSummary {
  tone: "good" | "bad" | "neutral";
  icon: typeof TrendingUp;
  text: string;
}

function summariseDelta(e: ScheduleResolveEvent): DeltaSummary {
  // Status transition takes precedence
  if (e.before_status && e.before_status !== e.after_status) {
    const goodTransitions = new Set(["INFEASIBLE>OPTIMAL", "INFEASIBLE>FEASIBLE"]);
    const badTransitions = new Set(["OPTIMAL>INFEASIBLE", "FEASIBLE>INFEASIBLE"]);
    const key = `${e.before_status}>${e.after_status}`;
    if (goodTransitions.has(key)) {
      return {
        tone: "good",
        icon: CheckCircle2,
        text: `${e.before_status} → ${e.after_status}`,
      };
    }
    if (badTransitions.has(key)) {
      return {
        tone: "bad",
        icon: XCircle,
        text: `${e.before_status} → ${e.after_status}`,
      };
    }
    return {
      tone: "neutral",
      icon: ArrowRight,
      text: `${e.before_status} → ${e.after_status}`,
    };
  }
  // Same status — compare objective if available (lower = better in our solver)
  if (e.before_objective !== null && e.after_objective !== null) {
    const delta = e.after_objective - e.before_objective;
    const pct = e.before_objective !== 0
      ? Math.round((delta / Math.abs(e.before_objective)) * 100)
      : 0;
    if (Math.abs(pct) < 1) {
      return {
        tone: "neutral",
        icon: ArrowRight,
        text: `${e.after_status} · ~same`,
      };
    }
    return {
      tone: delta < 0 ? "good" : "bad",
      icon: delta < 0 ? TrendingDown : TrendingUp,
      text: `${e.after_status} · objective ${delta < 0 ? "-" : "+"}${Math.abs(pct)}%`,
    };
  }
  return {
    tone: "neutral",
    icon: ArrowRight,
    text: e.after_status,
  };
}

function ScheduleEventRow({ event }: { event: ScheduleResolveEvent }) {
  const delta = summariseDelta(event);
  const Icon = delta.icon;
  const toneCls = {
    good: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
    bad: "border-red-500/40 bg-red-500/10 text-red-200",
    neutral: "border-white/10 bg-white/5 text-white/70",
  }[delta.tone];
  return (
    <li
      data-testid="schedule-history-row"
      data-tone={delta.tone}
      className="flex items-start justify-between gap-3 rounded-lg border border-white/5 bg-black/20 p-3"
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
              toneCls,
            )}
          >
            <Icon className="h-2.5 w-2.5" />
            {delta.text}
          </span>
          <span className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-white/50">
            {event.triggered_by}
          </span>
          {event.solve_time_ms !== null ? (
            <span className="text-[10px] text-white/40">
              <Clock className="mr-0.5 inline h-2.5 w-2.5" />
              {event.solve_time_ms}ms
            </span>
          ) : null}
        </div>
        {event.notes ? (
          <p className="mt-1 text-xs text-white/55">{event.notes}</p>
        ) : null}
        {event.before_slot_count !== null && event.after_slot_count !== null ? (
          <p className="mt-1 text-[11px] text-white/40">
            Slots {event.before_slot_count} → {event.after_slot_count}
          </p>
        ) : null}
      </div>
      <div className="shrink-0 text-right text-[11px] text-white/40">
        {event.at ? formatDate(event.at) : ""}
      </div>
    </li>
  );
}
