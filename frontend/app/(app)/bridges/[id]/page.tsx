"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Building2,
  Calendar,
  Droplet,
  MapPin,
  Phone,
  ShieldCheck,
  Users,
} from "lucide-react";

import { HealthBadge } from "@/components/ui/health-badge";
import { PendingRecruitsStrip } from "@/components/ui/pending-recruits-strip";
import { ScheduleHistoryPanel } from "@/components/ui/schedule-history-panel";
import { ScheduleTimeline } from "@/components/ui/schedule-timeline";
import { StabilityPanel } from "@/components/ui/stability-panel";
import { SwapPanel } from "@/components/ui/swap-panel";
import { api } from "@/lib/api";
import { cn, displayOr, formatDate, formatDaysRelative, isMissing } from "@/lib/utils";

export default function BridgeDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;

  const { data, isLoading, error } = useQuery({
    queryKey: ["bridge", id],
    queryFn: () => api.getBridge(id as string),
    enabled: Boolean(id),
  });

  if (isLoading) {
    return (
      <div className="px-8 py-8">
        <div className="h-8 w-64 animate-pulse rounded bg-surface/40" />
        <div className="mt-6 h-48 animate-pulse rounded-xl bg-surface/40" />
        <div className="mt-4 h-96 animate-pulse rounded-xl bg-surface/40" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="px-8 py-8">
        <Link
          href="/bridges"
          className="inline-flex items-center gap-2 text-sm text-white/70 hover:text-white"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to bridges
        </Link>
        <p className="mt-6 text-red-300">
          Could not load this bridge. {error?.message ?? "Unknown error."}
        </p>
      </div>
    );
  }

  const { patient, members } = data;

  return (
    <div className="px-8 py-8">
      <Link
        href="/bridges"
        className="inline-flex items-center gap-2 text-sm text-white/60 hover:text-white"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to bridges
      </Link>

      {/* --- Patient header --- */}
      <header className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-wider text-white/40">
            {data.name}
          </p>
          <h1 className="mt-1 text-3xl font-bold text-white">
            {patient.name}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-white/70">
            <span className="rounded-md bg-white/5 px-2 py-0.5 font-mono text-primary">
              {patient.blood_group}
            </span>
            <span>{patient.age} years old</span>
            <span className="text-white/30">·</span>
            <MapPin className="h-3.5 w-3.5" /> {displayOr(patient.city)}, {displayOr(patient.state)}
            {!isMissing(patient.hospital) && (
              <>
                <span className="text-white/30">·</span>
                <Building2 className="h-3.5 w-3.5" /> {displayOr(patient.hospital)}
              </>
            )}
          </div>
        </div>
        <HealthBadge health={data.health} />
      </header>

      {/* --- Stats row --- */}
      <section className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          icon={Users}
          label="Active donors"
          value={`${data.active_donor_count} / ${data.total_donor_count}`}
        />
        <StatCard
          icon={Calendar}
          label="Cadence"
          value={`every ${patient.transfusion_cadence_days}d`}
        />
        <StatCard
          icon={Droplet}
          label="Last transfusion"
          value={formatDate(patient.last_transfusion_date)}
        />
        <StatCard
          icon={Calendar}
          label="Next transfusion"
          value={formatDaysRelative(data.days_until_transfusion)}
        />
      </section>

      {/* --- Pending recruits (G1) --- */}
      <div className="mt-8">
        <PendingRecruitsStrip bridgeId={data.id} />
      </div>

      {/* --- Schedule resolve history (G3) --- */}
      <div className="mt-4">
        <ScheduleHistoryPanel bridgeId={data.id} />
      </div>

      {/* --- Slot swap state machine (G6) --- */}
      <div className="mt-4">
        <SwapPanel bridgeId={data.id} />
      </div>

      {/* --- Cohort --- */}
      <section className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Cohort</h2>
          <p className="text-xs text-white/40">
            {members.length} donor{members.length === 1 ? "" : "s"} · sorted by tenure
          </p>
        </div>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {members.map((m) => {
            // Highlight at-risk donors instead of pinning on a synthetic name.
            // A response_rate <= 0.5 reliably surfaces the destabilizers in any
            // dataset (real or synthetic).
            const atRisk = (m.donor.response_rate ?? 1) <= 0.5;
            return (
              <div
                key={m.id}
                className={cn(
                  "rounded-xl border bg-surface/30 p-4 transition-colors",
                  atRisk
                    ? "border-amber-500/40 bg-amber-500/5"
                    : "border-white/5 hover:border-white/10",
                )}
                data-testid="cohort-member"
                data-at-risk={atRisk}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-white">{m.donor.name}</h3>
                      {m.donor.kell_negative ? (
                        <ShieldCheck
                          className="h-3.5 w-3.5 text-accent"
                          aria-label="Kell-negative — preferred for repeat-transfused patients"
                        />
                      ) : null}
                    </div>
                    <p className="text-xs text-white/50">
                      {m.donor.age} · {m.donor.city}
                    </p>
                  </div>
                  <span className="rounded bg-white/5 px-2 py-0.5 font-mono text-xs text-white/80">
                    {m.donor.blood_group}
                  </span>
                </div>

                <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-white/60">
                  <div>
                    <span className="text-white/40">Joined: </span>
                    {formatDate(m.joined_at)}
                  </div>
                  <div>
                    <span className="text-white/40">Last donation: </span>
                    {formatDate(m.donor.last_donation_date)}
                  </div>
                  <div>
                    <span className="text-white/40">Total: </span>
                    {m.donor.total_donations}
                  </div>
                  <div>
                    <span className="text-white/40">Response: </span>
                    {Math.round(m.donor.response_rate * 100)}%
                  </div>
                </div>

                <div className="mt-3 flex items-center gap-3 text-xs text-white/40">
                  <Phone className="h-3 w-3" />
                  <span>{m.role}</span>
                  <span>·</span>
                  <span className="capitalize">{m.status}</span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* --- ML cohort stability --- */}
      <StabilityPanel bridgeId={data.id} />

      {/* --- OR-Tools rotation schedule --- */}
      <ScheduleTimeline bridgeId={data.id} />

    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Users;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-white/5 bg-surface/30 p-4">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="mt-1.5 text-base font-semibold text-white">{value}</div>
    </div>
  );
}
