"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertOctagon,
  CheckCircle2,
  Clock,
  Siren,
  XCircle,
  Zap,
} from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Operational metrics for the Alert Allocator. Lives on /analytics.
 *
 * Surfaces pings-per-acceptance (efficiency), avg time-to-accept by urgency
 * (speed), donor-fatigue distribution (load balancing), and recent
 * emergency events. The allocator is fully automated — no manual queue.
 */
export function OutreachAnalyticsPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["outreach-analytics"],
    queryFn: () => api.getOutreachAnalytics(30),
    staleTime: 60_000,
    retry: false,
  });

  if (isLoading) {
    return (
      <div
        data-testid="outreach-panel-loading"
        className="rounded-xl border border-white/5 bg-surface/40 p-5"
      >
        <div className="h-32 animate-pulse rounded-lg bg-white/5" />
      </div>
    );
  }

  if (!data) return null;

  const pingsPerAcc = data.pings.pings_per_acceptance;
  const acceptanceRate =
    data.pings.total > 0 ? (data.pings.accepted / data.pings.total) * 100 : 0;

  return (
    <section
      data-testid="outreach-analytics-panel"
      className="rounded-xl border border-white/5 bg-surface/40 p-5"
    >
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-white/40">
            <Zap className="h-4 w-4 text-accent" />
            Alert Allocator — last {data.lookback_days}d
          </h2>
          <p className="mt-0.5 text-[11px] text-white/40">
            Automated outreach waves and emergency events
          </p>
        </div>
      </div>

      {/* --- Top KPI row --- */}
      <div
        className="grid grid-cols-1 gap-3 sm:grid-cols-3"
        data-testid="outreach-kpis"
      >
        <KPI
          icon={CheckCircle2}
          tone="emerald"
          label="Acceptance rate"
          value={`${acceptanceRate.toFixed(0)}%`}
          hint={`${data.pings.accepted} of ${data.pings.total} pings`}
        />
        <KPI
          icon={Zap}
          tone="sky"
          label="Pings / acceptance"
          value={pingsPerAcc.toFixed(2)}
          hint="Lower = more efficient"
        />
        <KPI
          icon={Siren}
          tone="red"
          label="Emergency events"
          value={String(data.emergency.total)}
          hint={`${data.emergency.active} active`}
        />
      </div>

      {/* --- Wave outcome mini bar --- */}
      <div
        className="mt-4 rounded-lg border border-white/5 bg-black/20 p-3"
        data-testid="wave-mix"
      >
        <div className="mb-1.5 flex items-center justify-between text-[10px] uppercase tracking-wider text-white/40">
          <span>Wave outcomes</span>
          <span>{data.waves.total} total</span>
        </div>
        {data.waves.total === 0 ? (
          <p className="text-xs text-white/40">
            No waves in this window — fire the allocator from the
            Recommendations dashboard.
          </p>
        ) : (
          <>
            <WaveMixBar
              accepted={data.waves.accepted}
              active={data.waves.active}
              expired={data.waves.expired}
              total={data.waves.total}
            />
            <div className="mt-2 grid grid-cols-3 gap-2 text-[10px] text-white/55">
              <Legend color="bg-emerald-400/70" label={`Accepted (${data.waves.accepted})`} />
              <Legend color="bg-sky-400/70" label={`Active (${data.waves.active})`} />
              <Legend color="bg-red-400/70" label={`Expired (${data.waves.expired})`} />
            </div>
          </>
        )}
      </div>

      {/* --- Donor fatigue distribution --- */}
      <div
        className="mt-4 rounded-lg border border-white/5 bg-black/20 p-3"
        data-testid="fatigue-distribution"
      >
        <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-wider text-white/40">
          <span>Donor fatigue (pings in last 30d)</span>
        </div>
        <div className="grid grid-cols-5 gap-2 text-center text-[11px]">
          {(["0", "1", "2", "3-5", "6+"] as const).map((bucket) => {
            const count = data.donor_fatigue[bucket] ?? 0;
            return (
              <div
                key={bucket}
                className="rounded border border-white/5 bg-white/5 p-2"
                data-testid={`fatigue-bucket-${bucket}`}
              >
                <p className="font-mono text-lg text-white">{count}</p>
                <p className="text-[10px] text-white/40">{bucket} pings</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* --- Recent emergencies --- */}
      {data.emergency.recent.length > 0 ? (
        <div
          className="mt-4 rounded-lg border border-red-400/20 bg-red-500/5 p-3"
          data-testid="recent-emergencies"
        >
          <div className="mb-2 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-red-200/70">
            <AlertOctagon className="h-3 w-3" />
            Recent emergencies
          </div>
          <ul className="space-y-1">
            {data.emergency.recent.map((e) => (
              <li
                key={e.id}
                className="flex items-center justify-between text-[11px]"
              >
                <span className="truncate text-white/80">
                  {e.hospital_name ?? "—"} · by{" "}
                  <span className="text-white/60">{e.triggered_by}</span>
                </span>
                <span className="font-mono text-red-200">
                  {e.pool_size_at_trigger} reachable · {e.status}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function KPI({
  icon: Icon,
  tone,
  label,
  value,
  hint,
}: {
  icon: typeof CheckCircle2;
  tone: "emerald" | "sky" | "amber" | "red";
  label: string;
  value: string;
  hint: string;
}) {
  const tones = {
    emerald: "border-emerald-400/30 bg-emerald-500/5 text-emerald-200",
    sky: "border-sky-400/30 bg-sky-500/5 text-sky-200",
    amber: "border-amber-400/30 bg-amber-500/5 text-amber-200",
    red: "border-red-400/30 bg-red-500/5 text-red-200",
  }[tone];
  return (
    <div className={cn("rounded-lg border p-3", tones)} data-testid="outreach-kpi">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider opacity-70">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <div className="mt-1 text-xl font-bold tabular-nums">{value}</div>
      <p className="text-[10px] opacity-60">{hint}</p>
    </div>
  );
}

function WaveMixBar({
  accepted,
  active,
  expired,
  total,
}: {
  accepted: number;
  active: number;
  expired: number;
  total: number;
}) {
  const a = (accepted / total) * 100;
  const c = (active / total) * 100;
  const x = (expired / total) * 100;
  return (
    <div className="flex h-2.5 overflow-hidden rounded-full bg-black/40">
      <div className="bg-emerald-400/70" style={{ width: `${a}%` }} />
      <div className="bg-sky-400/70" style={{ width: `${c}%` }} />
      <div className="bg-red-400/70" style={{ width: `${x}%` }} />
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={cn("h-2 w-2 rounded-sm", color)} />
      <span className="text-white/55">{label}</span>
    </span>
  );
}
