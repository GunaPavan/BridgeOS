"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  CheckCircle2,
  Clock,
  Repeat2,
  XCircle,
} from "lucide-react";

import { api, type SwapRequest, type SwapStatus } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";

/**
 * G6 — Bridge detail panel showing all swap requests (proposed / accepted /
 * rejected / expired). Polls every 6s so a coordinator sees state flip when
 * donor B replies on WhatsApp.
 */
export function SwapPanel({ bridgeId }: { bridgeId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["swap-requests", bridgeId],
    queryFn: () => api.getSwapRequests(bridgeId, 10),
    refetchInterval: 6000,
    staleTime: 4000,
  });

  if (isLoading || !data || data.swaps.length === 0) return null;

  return (
    <section
      data-testid="swap-panel"
      className="rounded-xl border border-white/5 bg-surface/40 p-4"
    >
      <div className="mb-3 flex items-center gap-2">
        <Repeat2 className="h-4 w-4 text-accent" />
        <h2 className="text-sm font-semibold text-white">Slot swaps</h2>
        <span className="text-[10px] uppercase tracking-wider text-white/40">
          {data.swaps.length}
        </span>
      </div>
      <ul className="space-y-2">
        {data.swaps.map((s) => (
          <SwapRow key={s.id} swap={s} />
        ))}
      </ul>
    </section>
  );
}

const STATUS_STYLE: Record<
  SwapStatus,
  { pill: string; icon: typeof Clock; label: string }
> = {
  proposed: {
    pill: "border-amber-500/40 bg-amber-500/10 text-amber-200",
    icon: Clock,
    label: "Awaiting YES",
  },
  accepted: {
    pill: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
    icon: CheckCircle2,
    label: "Accepted",
  },
  rejected: {
    pill: "border-red-500/40 bg-red-500/10 text-red-200",
    icon: XCircle,
    label: "Declined",
  },
  expired: {
    pill: "border-white/10 bg-white/5 text-white/40",
    icon: Clock,
    label: "Expired",
  },
  cancelled: {
    pill: "border-white/10 bg-white/5 text-white/40",
    icon: XCircle,
    label: "Cancelled",
  },
};

function SwapRow({ swap }: { swap: SwapRequest }) {
  const style = STATUS_STYLE[swap.status];
  const Icon = style.icon;
  return (
    <li
      data-testid="swap-row"
      data-status={swap.status}
      className="flex items-start justify-between gap-3 rounded-lg border border-white/5 bg-black/20 p-3"
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
              style.pill,
            )}
          >
            <Icon className="h-2.5 w-2.5" />
            {style.label}
          </span>
        </div>
        <p className="mt-1 text-sm text-white">
          <span className="font-medium">{swap.from_donor_name}</span>
          <span className="mx-1 text-white/40">
            <ArrowLeftRight className="inline h-3 w-3" />
          </span>
          <span className="font-medium">{swap.to_donor_name}</span>
        </p>
        <p className="mt-0.5 text-[11px] text-white/55">
          {formatDate(swap.from_slot_date)} ↔ {formatDate(swap.to_slot_date)}
        </p>
      </div>
      <div className="shrink-0 text-right text-[11px] text-white/40">
        {swap.created_at ? formatDate(swap.created_at) : ""}
      </div>
    </li>
  );
}
