"use client";

import { Fragment } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertOctagon,
  ArrowLeft,
  CheckCircle2,
  Clock,
  PhoneCall,
  Send,
  UserMinus,
  XCircle,
} from "lucide-react";

import { PingFollowupTimeline } from "@/components/ui/ping-followup-timeline";
import { api } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";

const STATUS_PILL: Record<string, string> = {
  active: "border-sky-400/40 bg-sky-500/15 text-sky-200",
  accepted: "border-emerald-400/40 bg-emerald-500/15 text-emerald-200",
  expired: "border-red-400/40 bg-red-500/15 text-red-200",
  cancelled: "border-white/15 bg-white/5 text-white/50",
};

const PING_PILL: Record<string, string> = {
  pending: "border-amber-400/40 bg-amber-500/10 text-amber-200",
  accepted: "border-emerald-400/40 bg-emerald-500/10 text-emerald-200",
  declined: "border-red-400/40 bg-red-500/10 text-red-200",
  no_reply: "border-white/15 bg-white/5 text-white/50",
  cancelled: "border-white/15 bg-white/5 text-white/40",
};

export default function WaveDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["outreach-wave", id],
    queryFn: () => api.getOutreachWave(id as string),
    enabled: Boolean(id),
    refetchInterval: 15_000,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["outreach-wave", id] });

  const dispatch = useMutation({
    mutationFn: (override: boolean) => api.dispatchWave(id as string, override),
    onSuccess: refresh,
  });

  const promote = useMutation({
    mutationFn: () => api.promoteWaveToManual(id as string),
    onSuccess: refresh,
  });

  const exclude = useMutation({
    mutationFn: (donorId: string) => api.forceExcludeDonor(id as string, donorId),
    onSuccess: refresh,
  });

  if (isLoading) {
    return (
      <div className="px-8 py-8">
        <div className="h-8 w-64 animate-pulse rounded bg-surface/40" />
        <div className="mt-6 h-48 animate-pulse rounded-xl bg-surface/40" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="px-8 py-8">
        <Link
          href="/outreach"
          className="inline-flex items-center gap-1 text-sm text-white/60 hover:text-white"
        >
          <ArrowLeft className="h-3 w-3" /> Back to waves
        </Link>
        <p className="mt-4 text-sm text-red-300">
          Couldn&apos;t load wave: {error?.message ?? "not found"}
        </p>
      </div>
    );
  }

  const wave = data;
  const isActive = wave.status === "active";
  const pingCounts = wave.pings.reduce<Record<string, number>>((acc, p) => {
    acc[p.response] = (acc[p.response] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="px-8 py-8" data-testid="wave-detail-page">
      <Link
        href="/outreach"
        className="inline-flex items-center gap-1 text-sm text-white/60 hover:text-white"
      >
        <ArrowLeft className="h-3 w-3" /> Back to waves
      </Link>

      <header className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <AlertOctagon className="h-3.5 w-3.5" />
            {wave.tier.replace(/_/g, " ")} · slot {wave.slot_date}
          </div>
          <h1 className="mt-1 text-2xl font-bold text-white">
            Wave <span className="font-mono text-base text-white/40">{wave.id.slice(0, 8)}</span>
          </h1>
          <p className="mt-1 text-xs text-white/50">
            Triggered by {wave.triggered_by} · gap {wave.gap_days_at_creation}d · pool{" "}
            {wave.pool_size_at_creation}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "rounded-full border px-3 py-1 text-xs uppercase tracking-wider",
              STATUS_PILL[wave.status],
            )}
            data-testid="wave-status-pill"
          >
            {wave.status}
          </span>
          <span className="rounded-md border border-white/10 px-2 py-1 font-mono text-xs text-white/70">
            P_accept {(wave.realised_p_accept * 100).toFixed(0)}%/
            {(wave.target_p_accept * 100).toFixed(0)}%
          </span>
        </div>
      </header>

      {/* Action row */}
      <section className="mt-6 flex flex-wrap gap-2" data-testid="wave-actions">
        <button
          type="button"
          onClick={() => dispatch.mutate(false)}
          disabled={!isActive || dispatch.isPending}
          data-testid="dispatch-button"
          className="inline-flex items-center gap-2 rounded-md border border-primary/40 bg-primary/15 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/25 disabled:opacity-40"
        >
          <Send className="h-3 w-3" /> Dispatch
        </button>
        <button
          type="button"
          onClick={() => dispatch.mutate(true)}
          disabled={!isActive || dispatch.isPending}
          data-testid="dispatch-emergency-button"
          className="inline-flex items-center gap-2 rounded-md border border-red-400/40 bg-red-500/15 px-3 py-1.5 text-xs font-semibold text-red-200 hover:bg-red-500/25 disabled:opacity-40"
        >
          <Send className="h-3 w-3" /> Dispatch (override quiet hrs)
        </button>
        <button
          type="button"
          onClick={() => promote.mutate()}
          disabled={!isActive || promote.isPending}
          data-testid="promote-manual-button"
          className="inline-flex items-center gap-2 rounded-md border border-amber-400/40 bg-amber-500/15 px-3 py-1.5 text-xs font-semibold text-amber-200 hover:bg-amber-500/25 disabled:opacity-40"
        >
          <PhoneCall className="h-3 w-3" /> Promote to manual queue
        </button>
      </section>

      {/* Ping counts */}
      <section className="mt-6 grid grid-cols-5 gap-2 text-center text-xs" data-testid="ping-mix">
        {(["pending", "accepted", "declined", "no_reply", "cancelled"] as const).map((r) => (
          <div
            key={r}
            data-testid={`ping-count-${r}`}
            className={cn("rounded-md border p-2", PING_PILL[r])}
          >
            <p className="font-mono text-lg">{pingCounts[r] ?? 0}</p>
            <p className="text-[10px] uppercase tracking-wider opacity-70">{r.replace("_", " ")}</p>
          </div>
        ))}
      </section>

      {/* Pings table */}
      <section className="mt-6 rounded-xl border border-white/5 bg-surface/40 p-3">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-white/60">
            {wave.pings.length} pings
          </h2>
          <p className="text-[10px] uppercase tracking-wider text-white/40">
            Follow-up timeline under each row · Sent → Nudged → Reminded → Thanked
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs" data-testid="pings-table">
            <thead className="text-white/40">
              <tr>
                <th className="px-2 py-1">Donor</th>
                <th className="px-2 py-1">Channel</th>
                <th className="px-2 py-1">Response</th>
                <th className="px-2 py-1">Sent</th>
                <th className="px-2 py-1 text-right">Score</th>
                <th className="px-2 py-1 text-right">r_i</th>
                <th className="px-2 py-1"> </th>
              </tr>
            </thead>
            <tbody>
              {wave.pings.map((p) => (
                <Fragment key={p.id}>
                  <tr className="border-t border-white/5" data-testid="ping-row">
                    <td className="px-2 py-1">
                      <Link href={`/donors/${p.donor_id}`} className="text-white/80 hover:text-white">
                        {p.donor_id.slice(0, 8)}
                      </Link>
                    </td>
                    <td className="px-2 py-1 text-white/60">{p.channel}</td>
                    <td className="px-2 py-1">
                      <span
                        className={cn(
                          "rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider",
                          PING_PILL[p.response],
                        )}
                      >
                        {p.response.replace("_", " ")}
                      </span>
                    </td>
                    <td className="px-2 py-1 text-white/50">
                      {p.sent_at ? formatDate(p.sent_at) : "—"}
                    </td>
                    <td className="px-2 py-1 text-right font-mono text-white/60">
                      {p.composite_score.toFixed(2)}
                    </td>
                    <td className="px-2 py-1 text-right font-mono text-white/60">
                      {p.adjusted_response_rate.toFixed(2)}
                    </td>
                    <td className="px-2 py-1 text-right">
                      {p.response === "pending" && isActive ? (
                        <button
                          type="button"
                          onClick={() => exclude.mutate(p.donor_id)}
                          disabled={exclude.isPending}
                          data-testid="force-exclude-button"
                          className="inline-flex items-center gap-1 rounded border border-red-400/40 px-1.5 py-0.5 text-[10px] text-red-200 hover:bg-red-500/15"
                        >
                          <UserMinus className="h-2.5 w-2.5" /> Drop
                        </button>
                      ) : null}
                    </td>
                  </tr>
                  <tr data-testid="ping-followup-row">
                    <td colSpan={7} className="px-2 pb-2 pt-0">
                      <PingFollowupTimeline pingId={p.id} />
                    </td>
                  </tr>
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
