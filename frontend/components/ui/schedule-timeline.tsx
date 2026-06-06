"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Calendar,
  CheckCircle2,
  Clock,
  RefreshCw,
  Sigma,
  Users,
} from "lucide-react";
import Link from "next/link";

import { api, type ScheduleSlot } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";

// Stable color palette — slot color is keyed off donor index in the load list
const DONOR_COLORS = [
  "border-rose-500/40 bg-rose-500/10 text-rose-200",
  "border-amber-500/40 bg-amber-500/10 text-amber-200",
  "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
  "border-cyan-500/40 bg-cyan-500/10 text-cyan-200",
  "border-indigo-500/40 bg-indigo-500/10 text-indigo-200",
  "border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-200",
  "border-orange-500/40 bg-orange-500/10 text-orange-200",
  "border-lime-500/40 bg-lime-500/10 text-lime-200",
  "border-pink-500/40 bg-pink-500/10 text-pink-200",
  "border-sky-500/40 bg-sky-500/10 text-sky-200",
];

export function ScheduleTimeline({ bridgeId }: { bridgeId: string }) {
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["schedule", bridgeId],
    queryFn: () => api.getBridgeSchedule(bridgeId, { horizonDays: 365 }),
    retry: false,
  });

  const resolveMutation = useMutation({
    mutationFn: () => api.resolveBridgeSchedule(bridgeId),
    onSuccess: (fresh) => {
      queryClient.setQueryData(["schedule", bridgeId], fresh);
    },
  });

  if (isLoading) {
    return (
      <section className="mt-8">
        <h2 className="mb-3 text-lg font-semibold text-white">Rotation Schedule</h2>
        <div className="h-64 animate-pulse rounded-xl bg-surface/40" />
      </section>
    );
  }

  if (error) {
    const is422 = /422/.test(error.message) || /infeasible/i.test(error.message);
    return (
      <section className="mt-8" data-testid="schedule-timeline-error">
        <h2 className="mb-3 text-lg font-semibold text-white">Rotation Schedule</h2>
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-200/90">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" />
            {is422 ? "Rotation is infeasible" : "Could not load schedule"}
          </div>
          <p className="mt-1 text-amber-200/70">{error.message}</p>
          {is422 ? (
            <>
              <p className="mt-2 text-amber-200/70">
                Not enough eligible donors to cover the patient's transfusion cadence.
                Recruit additional donors and the scheduler will re-solve automatically.
              </p>
              <Link
                href="/recommendations"
                data-testid="schedule-infeasible-cta"
                className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-100 hover:border-amber-400/60 hover:bg-amber-500/15"
              >
                View recruitment recommendations
                <ArrowRight className="h-3 w-3" />
              </Link>
            </>
          ) : null}
        </div>
      </section>
    );
  }

  if (!data) return null;

  // Color lookup keyed by donor id, in donor_load order (sorted desc by count for stability)
  const sortedLoad = [...data.donor_load].sort(
    (a, b) => b.assignment_count - a.assignment_count,
  );
  const colorForDonor = new Map(
    sortedLoad.map((d, i) => [d.donor_id, DONOR_COLORS[i % DONOR_COLORS.length]]),
  );
  const maxLoad = Math.max(1, ...sortedLoad.map((d) => d.assignment_count));

  return (
    <section className="mt-8" data-testid="schedule-timeline">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Rotation Schedule</h2>
          <p className="text-xs text-white/50">
            OR-Tools CP-SAT · 12-month horizon · {data.transfusion_cadence_days}-day cadence
          </p>
        </div>
        <button
          type="button"
          onClick={() => resolveMutation.mutate()}
          disabled={resolveMutation.isPending}
          className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-white/70 hover:border-white/20 hover:text-white disabled:opacity-50"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${resolveMutation.isPending ? "animate-spin" : ""}`}
          />
          Re-solve
        </button>
      </div>

      {/* Solver stats */}
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SolverStat
          icon={CheckCircle2}
          label="Solver status"
          value={data.solver_status}
          tone={data.solver_status === "OPTIMAL" ? "ok" : "warn"}
        />
        <SolverStat
          icon={Clock}
          label="Solve time"
          value={`${data.solve_time_ms} ms`}
        />
        <SolverStat
          icon={Calendar}
          label="Transfusion slots"
          value={`${data.slots.length}`}
        />
        <SolverStat
          icon={Sigma}
          label="Objective"
          value={data.objective_value.toFixed(0)}
        />
      </div>

      {/* Donor load chart */}
      <div className="mb-4 rounded-xl border border-white/5 bg-surface/30 p-4">
        <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
          <Users className="h-3.5 w-3.5" />
          Donor load (assignments over 12 months)
        </div>
        <div className="space-y-1.5" data-testid="donor-load-chart">
          {sortedLoad.map((d) => {
            const pct = (d.assignment_count / maxLoad) * 100;
            const color = colorForDonor.get(d.donor_id) ?? DONOR_COLORS[0];
            return (
              <div key={d.donor_id} className="flex items-center gap-2 text-xs">
                <span className="w-32 shrink-0 truncate text-white/70" title={d.donor_name}>
                  {d.donor_name}
                </span>
                <div className="relative h-2 flex-1 rounded-full bg-white/5">
                  <div
                    className={cn("h-full rounded-full border", color)}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="w-8 shrink-0 text-right tabular-nums text-white">
                  {d.assignment_count}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Slot strip */}
      <div className="rounded-xl border border-white/5 bg-surface/30 p-4">
        <div className="mb-3 flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
          <Calendar className="h-3.5 w-3.5" />
          Solved rotation
        </div>
        <div
          className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5"
          data-testid="schedule-slots"
        >
          {data.slots.map((s) => (
            <ScheduleSlotCard
              key={s.sequence}
              slot={s}
              colorClasses={colorForDonor.get(s.donor_id) ?? DONOR_COLORS[0]}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

function ScheduleSlotCard({
  slot,
  colorClasses,
}: {
  slot: ScheduleSlot;
  colorClasses: string;
}) {
  return (
    <div
      className={cn("rounded-lg border p-3", colorClasses)}
      data-testid="schedule-slot"
    >
      <div className="flex items-center justify-between text-[10px] uppercase tracking-wider opacity-70">
        <span>#{slot.sequence}</span>
        <span className="font-mono">{slot.donor_blood_group}</span>
      </div>
      <p className="mt-1 text-sm font-semibold">{formatDate(slot.transfusion_date)}</p>
      <p className="truncate text-xs opacity-90" title={slot.donor_name}>
        {slot.donor_name}
      </p>
    </div>
  );
}

function SolverStat({
  icon: Icon,
  label,
  value,
  tone = "neutral",
}: {
  icon: typeof CheckCircle2;
  label: string;
  value: string;
  tone?: "ok" | "warn" | "neutral";
}) {
  const valueClass =
    tone === "ok"
      ? "text-emerald-300"
      : tone === "warn"
      ? "text-amber-300"
      : "text-white";
  return (
    <div className="rounded-xl border border-white/5 bg-surface/30 p-3">
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-white/40">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <div className={cn("mt-1 text-base font-semibold tabular-nums", valueClass)}>
        {value}
      </div>
    </div>
  );
}
