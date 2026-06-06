"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCircle2, Send, Sparkles } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface FollowUps {
  ping_id: string;
  wave_id: string;
  donor_id: string;
  response: string;
  sent_at: string | null;
  response_at: string | null;
  nudge: { count: number; last_sent_at: string | null };
  reminder: { sent_at: string | null };
  thank_you: { sent_at: string | null };
}

function fmtRelative(iso: string | null): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  const diff = Math.round((Date.now() - t) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

/**
 * Per-ping follow-up timeline.
 *
 * Stages: sent → nudged (N×) → reminded → thanked. Each stage is shown as a
 * pill: filled when complete, ghosted while pending.
 *
 * Embeds on /outreach/[id] under each ping row.
 */
export function PingFollowupTimeline({ pingId }: { pingId: string }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["ping-followups", pingId],
    queryFn: () => api.getPingFollowUps(pingId),
    refetchInterval: 8000,
  });

  const nudge = useMutation({
    mutationFn: () => api.triggerPingNudge(pingId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ping-followups", pingId] }),
  });

  if (isLoading || !data) {
    return (
      <div
        data-testid="ping-followup-timeline-loading"
        className="h-6 animate-pulse rounded bg-white/5"
      />
    );
  }

  const fu = data as FollowUps;
  const sentDone = Boolean(fu.sent_at);
  const nudgeDone = fu.nudge.count > 0;
  const reminderDone = Boolean(fu.reminder.sent_at);
  const thankedDone = Boolean(fu.thank_you.sent_at);

  return (
    <div
      data-testid="ping-followup-timeline"
      data-ping-id={fu.ping_id}
      className="flex flex-wrap items-center gap-1.5 text-[11px]"
    >
      <Stage
        Icon={Send}
        label="Sent"
        done={sentDone}
        timestamp={fu.sent_at}
        testId="stage-sent"
      />
      <Sep />
      <Stage
        Icon={Bell}
        label={fu.nudge.count > 0 ? `Nudged ×${fu.nudge.count}` : "Nudged"}
        done={nudgeDone}
        timestamp={fu.nudge.last_sent_at}
        testId="stage-nudged"
      />
      <Sep />
      <Stage
        Icon={Sparkles}
        label="Reminded"
        done={reminderDone}
        timestamp={fu.reminder.sent_at}
        testId="stage-reminded"
      />
      <Sep />
      <Stage
        Icon={CheckCircle2}
        label="Thanked"
        done={thankedDone}
        timestamp={fu.thank_you.sent_at}
        testId="stage-thanked"
      />

      {/* Manual nudge — only show while still nudge-eligible (PENDING) */}
      {fu.response === "pending" && (
        <button
          type="button"
          data-testid="manual-nudge-button"
          onClick={() => nudge.mutate()}
          disabled={nudge.isPending}
          className="ml-1 rounded-md border border-white/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-white/60 hover:border-primary/40 hover:text-primary disabled:opacity-50"
          title="Send the pending-ping nudge now (ignores 4h / 12h thresholds)"
        >
          Nudge now
        </button>
      )}
    </div>
  );
}

function Stage({
  Icon,
  label,
  done,
  timestamp,
  testId,
}: {
  Icon: typeof Send;
  label: string;
  done: boolean;
  timestamp: string | null;
  testId: string;
}) {
  return (
    <span
      data-testid={testId}
      data-done={done}
      title={timestamp ? new Date(timestamp).toLocaleString() : "Not yet"}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5",
        done
          ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
          : "bg-white/5 text-white/40 border border-white/5",
      )}
    >
      <Icon className="h-3 w-3" />
      {label}
      {done && timestamp ? (
        <span className="ml-1 font-mono text-[10px] text-white/45">
          {fmtRelative(timestamp)}
        </span>
      ) : null}
    </span>
  );
}

function Sep() {
  return <span className="text-white/20">·</span>;
}
