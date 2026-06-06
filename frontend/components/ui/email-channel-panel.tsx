"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Inbox, Mail, XCircle } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const TEMPLATE_LABELS: Record<string, string> = {
  caregiver_daily_digest: "Daily digest",
  caregiver_emergency_alert: "Emergency alert",
  coordinator_failure_alert: "Coordinator alert",
  ops_test: "Test sends",
};

/**
 * Email Channel Panel — embedded on /analytics.
 *
 * Shows the SES outbound stats over a window:
 *   - Sent / Failed / Mocked tallies (with bedrock-mode parity)
 *   - Per-template counts
 *   - Last 5 recipients
 *
 * Refetches every 30 seconds.
 */
export function EmailChannelPanel({ windowDays = 30 }: { windowDays?: number }) {
  const { data: dist, isLoading } = useQuery({
    queryKey: ["email-distribution", windowDays],
    queryFn: () => api.getEmailDistribution(windowDays),
    refetchInterval: 30_000,
  });
  const { data: recent } = useQuery({
    queryKey: ["email-recent"],
    queryFn: () => api.listEmails({ limit: 5 }),
    refetchInterval: 30_000,
  });

  if (isLoading || !dist) {
    return (
      <section
        data-testid="email-channel-loading"
        className="h-56 animate-pulse rounded-xl border border-white/5 bg-surface/30"
      />
    );
  }

  return (
    <section
      data-testid="email-channel-panel"
      className="rounded-xl border border-white/5 bg-surface/40 p-5"
    >
      <header className="mb-3 flex items-end justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-white/40">
            <Mail className="h-4 w-4 text-accent" />
            Email channel — last {dist.window_days}d
          </h2>
          <p className="mt-0.5 text-[11px] text-white/40">
            Amazon SES — daily caregiver digests, emergency alerts, ops alerts
          </p>
        </div>
        <div className="text-[11px] text-white/40">
          Mock sends count toward the total — they look identical in the audit log
        </div>
      </header>

      {/* Top KPI row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="email-kpis">
        <Kpi
          Icon={Inbox}
          tone="default"
          label="Total"
          value={String(dist.total)}
        />
        <Kpi
          Icon={CheckCircle2}
          tone="ok"
          label="Sent"
          value={String(dist.sent)}
        />
        <Kpi
          Icon={Mail}
          tone="warn"
          label="Mocked"
          value={String(dist.mocked)}
          hint="SES not configured"
        />
        <Kpi
          Icon={XCircle}
          tone="bad"
          label="Failed"
          value={String(dist.failed)}
        />
      </div>

      {/* Per-template breakdown */}
      {dist.by_template.length > 0 ? (
        <div className="mt-4" data-testid="email-by-template">
          <h3 className="mb-1.5 text-[10px] uppercase tracking-wider text-white/40">
            By template
          </h3>
          <ul className="space-y-1">
            {dist.by_template.map((b) => (
              <li
                key={b.template_key}
                className="flex items-center justify-between rounded border border-white/5 bg-black/20 px-2 py-1 text-xs text-white/80"
              >
                <span>{TEMPLATE_LABELS[b.template_key] ?? b.template_key}</span>
                <span className="flex items-center gap-2 font-mono text-[11px] text-white/60">
                  {b.sent > 0 ? <span className="text-emerald-300">✓ {b.sent}</span> : null}
                  {b.mocked > 0 ? <span className="text-amber-300">~ {b.mocked}</span> : null}
                  {b.failed > 0 ? <span className="text-red-300">✗ {b.failed}</span> : null}
                  {b.skipped > 0 ? <span className="text-white/40">- {b.skipped}</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-4 rounded-md border border-white/5 bg-black/20 p-4 text-center text-xs text-white/40">
          No emails sent in this window yet.
        </p>
      )}

      {/* Recent recipients */}
      {recent && recent.items.length > 0 ? (
        <div className="mt-4" data-testid="email-recent-list">
          <h3 className="mb-1.5 text-[10px] uppercase tracking-wider text-white/40">
            Recent recipients
          </h3>
          <ul className="space-y-1 text-xs text-white/65">
            {recent.items.slice(0, 5).map((e) => (
              <li
                key={e.id}
                className="flex items-center justify-between rounded border border-white/5 bg-black/20 px-2 py-1"
              >
                <span className="truncate font-mono">{e.recipient_email}</span>
                <span
                  className={cn(
                    "ml-2 shrink-0 rounded-full px-1.5 py-0.5 text-[10px] uppercase tracking-wider",
                    e.status === "sent"
                      ? "bg-emerald-500/15 text-emerald-300"
                      : e.status === "mocked"
                        ? "bg-amber-500/15 text-amber-300"
                        : e.status === "failed"
                          ? "bg-red-500/15 text-red-300"
                          : "bg-white/5 text-white/40",
                  )}
                >
                  {e.status}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function Kpi({
  Icon,
  tone,
  label,
  value,
  hint,
}: {
  Icon: typeof Mail;
  tone: "ok" | "warn" | "bad" | "default";
  label: string;
  value: string;
  hint?: string;
}) {
  const toneCls =
    tone === "ok"
      ? "text-emerald-300 border-emerald-500/30 bg-emerald-500/5"
      : tone === "warn"
        ? "text-amber-300 border-amber-500/30 bg-amber-500/5"
        : tone === "bad"
          ? "text-red-300 border-red-500/30 bg-red-500/5"
          : "text-white border-white/10 bg-black/15";
  return (
    <div
      data-testid="email-kpi"
      className={cn("rounded-md border p-3", toneCls)}
    >
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider opacity-80">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <p className="mt-0.5 text-lg font-semibold tabular-nums">{value}</p>
      {hint ? <p className="text-[10px] opacity-60">{hint}</p> : null}
    </div>
  );
}
