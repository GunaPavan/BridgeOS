"use client";

import { useQuery } from "@tanstack/react-query";
import { Brain, MessageSquare, Sparkles } from "lucide-react";

import { ReplyIntentBadge, type ReplyIntentValue } from "@/components/ui/reply-intent-badge";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Reply Intelligence Panel — on /analytics.
 *
 * Surfaces:
 *   - Intent distribution donut
 *   - Confidence histogram
 *   - Top 5 free-text reschedule reasons
 *   - Avg confidence + fallback rate
 *
 * Refreshes every 30 seconds.
 */
export function ReplyIntelligencePanel({ windowDays = 30 }: { windowDays?: number }) {
  const { data: dist, isLoading: distLoading } = useQuery({
    queryKey: ["reply-intent-distribution", windowDays],
    queryFn: () => api.getReplyIntentDistribution(windowDays),
    refetchInterval: 30_000,
  });
  const { data: hist } = useQuery({
    queryKey: ["reply-confidence-histogram", windowDays],
    queryFn: () => api.getReplyConfidenceHistogram(windowDays),
    refetchInterval: 30_000,
  });

  if (distLoading || !dist) {
    return (
      <section
        data-testid="reply-intelligence-loading"
        className="h-72 animate-pulse rounded-xl border border-white/5 bg-surface/30"
      />
    );
  }

  const total = dist.total;
  const totalSafe = Math.max(1, total);
  const orderedCounts = [...dist.counts].sort((a, b) => b.count - a.count);
  const maxBucket = Math.max(1, ...(hist ?? []).map((b) => b.count));

  return (
    <section
      data-testid="reply-intelligence-panel"
      className="rounded-xl border border-white/5 bg-surface/40 p-5"
    >
      <header className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-white/40">
            <Brain className="h-4 w-4 text-accent" />
            Reply intelligence — last {dist.window_days}d
          </h2>
          <p className="mt-0.5 text-[11px] text-white/40">
            Bedrock-classified donor replies (Claude Haiku 4.5)
          </p>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-white/50">
          <span title="Average classifier confidence">
            <span className="text-white/40">avg conf </span>
            <span className="font-mono text-white">
              {(dist.avg_confidence * 100).toFixed(0)}%
            </span>
          </span>
          <span title="Share of replies that fell back to the keyword parser">
            <span className="text-white/40">fallback </span>
            <span className="font-mono text-white">
              {(dist.fallback_rate * 100).toFixed(0)}%
            </span>
          </span>
        </div>
      </header>

      {total === 0 ? (
        <p className="rounded-md border border-white/5 bg-black/20 p-6 text-center text-xs text-white/50">
          No replies classified in this window yet.
        </p>
      ) : (
        <>
          {/* Distribution bar */}
          <div
            data-testid="intent-distribution"
            className="overflow-hidden rounded-md bg-white/5"
          >
            <div className="flex h-4 w-full">
              {orderedCounts.map((c) => (
                <div
                  key={c.intent}
                  data-testid={`intent-segment-${c.intent}`}
                  style={{ width: `${(c.count / totalSafe) * 100}%` }}
                  className={cn("h-full", _segmentColour(c.intent as ReplyIntentValue))}
                  title={`${c.intent}: ${c.count}`}
                />
              ))}
            </div>
          </div>

          {/* Legend */}
          <div
            className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4"
            data-testid="intent-legend"
          >
            {orderedCounts.map((c) => (
              <div key={c.intent} className="flex items-center justify-between gap-2">
                <ReplyIntentBadge intent={c.intent as ReplyIntentValue} />
                <span className="font-mono text-xs text-white/70">{c.count}</span>
              </div>
            ))}
          </div>

          {/* Confidence histogram */}
          {hist && hist.length > 0 ? (
            <div
              data-testid="confidence-histogram"
              className="mt-5 rounded-md border border-white/5 bg-black/20 p-3"
            >
              <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-wider text-white/40">
                <span>Confidence histogram</span>
                <span>10 buckets</span>
              </div>
              <div className="flex h-20 items-end gap-1">
                {hist.map((b) => (
                  <div
                    key={`${b.low}-${b.high}`}
                    data-testid={`hist-bucket-${(b.low * 10).toFixed(0)}`}
                    className="flex-1 rounded-t bg-accent/40"
                    style={{
                      height: `${(b.count / maxBucket) * 100}%`,
                      minHeight: b.count > 0 ? "4px" : "1px",
                    }}
                    title={`${(b.low * 100).toFixed(0)}-${(b.high * 100).toFixed(0)}%: ${b.count}`}
                  />
                ))}
              </div>
              <div className="mt-1 flex justify-between text-[9px] text-white/30 font-mono">
                <span>0</span>
                <span>0.5</span>
                <span>1.0</span>
              </div>
            </div>
          ) : null}

          {/* Top reschedule reasons */}
          {dist.top_reschedule_reasons.length > 0 ? (
            <div className="mt-5" data-testid="top-reschedule-reasons">
              <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-wider text-white/40">
                <Sparkles className="h-3 w-3" />
                Top reschedule reasons
              </div>
              <ul className="space-y-1 text-xs text-white/75">
                {dist.top_reschedule_reasons.map((r, i) => (
                  <li
                    key={i}
                    className="rounded border border-white/5 bg-black/20 px-2 py-1"
                  >
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}

function _segmentColour(intent: ReplyIntentValue): string {
  switch (intent) {
    case "accept":
      return "bg-emerald-500/70";
    case "decline":
      return "bg-red-500/70";
    case "reschedule_request":
      return "bg-sky-500/70";
    case "out_of_town":
      return "bg-amber-500/70";
    case "medical_defer":
      return "bg-violet-500/70";
    case "unrelated_question":
      return "bg-blue-500/70";
    case "stop":
      return "bg-zinc-500/70";
    default:
      return "bg-white/15";
  }
}
