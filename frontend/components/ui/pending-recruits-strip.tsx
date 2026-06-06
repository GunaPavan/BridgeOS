"use client";

import { useQuery } from "@tanstack/react-query";
import { Clock, Globe, MessageSquareText, UserPlus } from "lucide-react";

import { api } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";

/**
 * Bridge detail page strip — shows PENDING recruits awaiting donor YES on WhatsApp.
 * Polls every 4s so a coordinator sees state flip as soon as a donor replies.
 */
export function PendingRecruitsStrip({ bridgeId }: { bridgeId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["pending-recruits", bridgeId],
    queryFn: () => api.listPendingRecruits(bridgeId),
    refetchInterval: 4000,
  });

  if (isLoading || !data || data.length === 0) return null;

  return (
    <section
      data-testid="pending-recruits-strip"
      className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4"
    >
      <div className="mb-3 flex items-center gap-2">
        <Clock className="h-4 w-4 text-amber-300" />
        <h2 className="text-sm font-semibold text-amber-100">
          {data.length} pending recruit{data.length === 1 ? "" : "s"} — waiting on donor reply
        </h2>
      </div>
      <ul className="space-y-2">
        {data.map((p) => (
          <li
            key={p.membership_id}
            data-testid="pending-recruit-row"
            className="flex items-start justify-between gap-3 rounded-lg border border-white/5 bg-black/30 p-3"
          >
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <UserPlus className="h-3.5 w-3.5 text-amber-300" />
                <p className="font-medium text-white">
                  {p.candidate_donor_name}
                </p>
                <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-amber-200">
                  <Clock className="h-2.5 w-2.5" />
                  Pending YES
                </span>
              </div>
              <p className="mt-1 text-xs text-white/55">
                Invite sent {formatDate(p.joined_at)} ·{" "}
                <span className="inline-flex items-center gap-1 font-mono">
                  <Globe className="h-2.5 w-2.5" />
                  {p.invite_language ?? "en"}
                </span>
                {" · "}
                <span className="font-mono">{p.candidate_donor_phone}</span>
              </p>
              {p.replaces_donor_name ? (
                <p className="mt-1 text-xs text-white/45">
                  Will replace{" "}
                  <span className="text-white/70">{p.replaces_donor_name}</span>{" "}
                  on YES — they stay active in the meantime.
                </p>
              ) : (
                <p className="mt-1 text-xs text-white/45">
                  Will join the cohort on YES.
                </p>
              )}
            </div>
            <a
              href={`/whatsapp`}
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 rounded-md border border-white/10 px-2.5 py-1 text-[11px] text-white/70 hover:border-white/20 hover:text-white",
              )}
            >
              <MessageSquareText className="h-3 w-3" />
              View thread
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
