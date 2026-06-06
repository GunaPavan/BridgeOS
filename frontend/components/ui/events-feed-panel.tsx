"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Radio, Tag } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Events Feed Panel — embedded on /system/scheduler.
 *
 * Shows the SNS event bus status + the most recent published events.
 * Subscribers (in-process for now, Lambda after deploy) appear per topic.
 */
export function EventsFeedPanel() {
  const { data: status } = useQuery({
    queryKey: ["events-status"],
    queryFn: () => api.getEventsDispatcherStatus(),
    refetchInterval: 5_000,
  });
  const { data: recent } = useQuery({
    queryKey: ["events-recent"],
    queryFn: () => api.listRecentEvents(20),
    refetchInterval: 5_000,
  });

  if (!status) {
    return (
      <div
        data-testid="events-feed-loading"
        className="h-48 animate-pulse rounded-xl border border-white/5 bg-surface/30"
      />
    );
  }

  return (
    <div
      data-testid="events-feed-panel"
      className="rounded-xl border border-white/5 bg-surface/40 p-4"
    >
      <header className="mb-3 flex items-end justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-white/40">
            <Radio className="h-4 w-4 text-accent" />
            Event bus (SNS)
          </h3>
          <p className="mt-0.5 text-[11px] text-white/40">
            Donor reply + wave lifecycle events. In-process subscribers fan out
            cooldown, EMA, sibling cancel.
          </p>
        </div>
        <div className="text-[11px] text-white/40">
          {status.running ? (
            <span className="text-emerald-300">
              dispatcher running · {status.delivered} delivered, {status.failed} failed
            </span>
          ) : (
            <span className="text-red-300">dispatcher stopped</span>
          )}
        </div>
      </header>

      {/* Topics + subscribers */}
      <div className="mb-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3" data-testid="events-topics">
        {status.topics.map((t) => (
          <div
            key={t.topic}
            data-testid={`topic-${t.topic}`}
            className="rounded border border-white/5 bg-black/15 p-2"
          >
            <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-white/40">
              <Tag className="h-3 w-3" />
              {t.topic}
            </div>
            <p className="mt-0.5 truncate text-[11px] text-white/65">
              {t.subscribers.length === 0
                ? "(no subscribers)"
                : t.subscribers.join(", ")}
            </p>
          </div>
        ))}
      </div>

      {/* Recent events */}
      <div data-testid="events-recent">
        <h4 className="mb-1 text-[10px] uppercase tracking-wider text-white/40">
          Recent events
        </h4>
        {recent && recent.length > 0 ? (
          <ul className="space-y-1">
            {recent.slice(0, 10).map((e) => (
              <li
                key={e.message_id}
                data-testid="event-row"
                className="flex items-center justify-between gap-2 rounded border border-white/5 bg-black/15 px-2 py-1 text-xs"
              >
                <span className="truncate font-mono text-white/70">
                  {e.topic_name.replace(/^.+bridge-os-/, "")}
                </span>
                <span className="shrink-0 font-mono text-[10px] text-white/40">
                  {new Date(e.published_at).toLocaleTimeString()}
                </span>
                <span
                  className={cn(
                    "shrink-0 rounded-full px-1.5 py-0.5 text-[10px] uppercase tracking-wider",
                    e.is_mock
                      ? "bg-amber-500/15 text-amber-300"
                      : "bg-emerald-500/15 text-emerald-300",
                  )}
                >
                  {e.is_mock ? "mock" : "live"}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded border border-white/5 bg-black/15 p-3 text-center text-xs text-white/40">
            No events published yet — try sending a donor reply via /whatsapp.
          </p>
        )}
      </div>
    </div>
  );
}
