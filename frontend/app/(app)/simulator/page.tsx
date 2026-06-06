"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Brain,
  CheckCircle2,
  Clock,
  Grid3x3,
  Network,
  Play,
  RefreshCw,
  RotateCcw,
  Sparkles,
  Undo2,
  UserMinus,
  Users,
  Zap,
} from "lucide-react";

import { CohortGraph } from "@/components/ui/cohort-graph";
import { api, type CohortMemberState, type ScenarioOutcome } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";

type SimulatorView = "graph" | "grid";

export default function SimulatorPage() {
  // Load all bridges so the user can pick one
  const bridgesQuery = useQuery({
    queryKey: ["bridges", { limit: 200 }],
    queryFn: () => api.listBridges({ limit: 200 }),
  });

  const [bridgeId, setBridgeId] = useState<string | null>(null);
  const [ejected, setEjected] = useState<string[]>([]);
  const [view, setView] = useState<SimulatorView>("graph");

  // Pre-select Aarav's bridge when bridges arrive
  useEffect(() => {
    if (bridgeId === null && bridgesQuery.data) {
      const aarav = bridgesQuery.data.items.find(
        (b) => b.patient_name === "Aarav Reddy",
      );
      setBridgeId(aarav?.id ?? bridgesQuery.data.items[0]?.id ?? null);
    }
  }, [bridgesQuery.data, bridgeId]);

  const scenario = useMutation({
    mutationFn: ({ bid, eids }: { bid: string; eids: string[] }) =>
      api.runScenario(bid, eids),
  });

  // Run scenario whenever bridge or ejected set changes
  useEffect(() => {
    if (!bridgeId) return;
    scenario.mutate({ bid: bridgeId, eids: ejected });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bridgeId, ejected.join(",")]);

  const toggleEject = (donorId: string) => {
    setEjected((cur) =>
      cur.includes(donorId) ? cur.filter((id) => id !== donorId) : [...cur, donorId],
    );
  };

  const reset = () => setEjected([]);

  return (
    <div className="px-8 py-8">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Play className="h-3.5 w-3.5" />
            Simulator
          </div>
          <h1 className="mt-1 text-3xl font-bold text-white">
            Live cohort simulator
          </h1>
          <p className="mt-1 text-sm text-white/60">
            Eject a donor and watch the stability model, the OR-Tools scheduler,
            and the recommender re-run in milliseconds — without touching the database.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {ejected.length > 0 ? (
            <button
              type="button"
              onClick={reset}
              className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-white/70 hover:border-white/20 hover:text-white"
              data-testid="reset-button"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Reset ({ejected.length})
            </button>
          ) : null}
          <button
            type="button"
            onClick={() =>
              bridgeId && scenario.mutate({ bid: bridgeId, eids: ejected })
            }
            disabled={!bridgeId || scenario.isPending}
            className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-white/70 hover:border-white/20 hover:text-white disabled:opacity-50"
          >
            <RefreshCw
              className={cn("h-3.5 w-3.5", scenario.isPending && "animate-spin")}
            />
            Re-run
          </button>
        </div>
      </header>

      {/* Bridge picker */}
      <section className="mb-6 rounded-xl border border-white/5 bg-surface/30 p-4">
        <label className="flex items-center gap-3 text-sm text-white/70">
          <span className="text-xs uppercase tracking-wider text-white/40">
            Bridge
          </span>
          {bridgesQuery.isLoading ? (
            <span className="text-white/40">Loading bridges…</span>
          ) : (
            <select
              value={bridgeId ?? ""}
              onChange={(e) => {
                setEjected([]);
                setBridgeId(e.target.value);
              }}
              className="flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white focus:border-primary/50 focus:outline-none"
              data-testid="bridge-picker"
            >
              {bridgesQuery.data?.items.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.patient_name} ({b.blood_group}) · {b.active_donor_count} donors ·{" "}
                  {b.city}
                </option>
              ))}
            </select>
          )}
        </label>
      </section>

      {scenario.error ? (
        <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" />
            Scenario failed
          </div>
          <p className="mt-1 text-red-300/80">{scenario.error.message}</p>
        </div>
      ) : null}

      {scenario.data ? (
        <SimulatorBody
          outcome={scenario.data}
          ejected={ejected}
          onToggleEject={toggleEject}
          pending={scenario.isPending}
          view={view}
          onViewChange={setView}
          selectedBridge={
            bridgesQuery.data?.items.find((b) => b.id === bridgeId) ?? null
          }
        />
      ) : scenario.isPending ? (
        <SimulatorSkeleton />
      ) : null}
    </div>
  );
}

function SimulatorBody({
  outcome,
  ejected,
  onToggleEject,
  pending,
  view,
  onViewChange,
  selectedBridge,
}: {
  outcome: ScenarioOutcome;
  ejected: string[];
  onToggleEject: (donorId: string) => void;
  pending: boolean;
  view: SimulatorView;
  onViewChange: (v: SimulatorView) => void;
  selectedBridge:
    | { patient_name: string; blood_group: string }
    | null;
}) {
  const ejectedSet = new Set(ejected);

  return (
    <div className="space-y-6" data-testid="simulator-body">
      {/* Delta summary */}
      <DeltaBanner outcome={outcome} />

      {/* Cohort visualisation */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Cohort</h2>
          <div className="flex items-center gap-3">
            <p className="text-xs text-white/40">
              {outcome.baseline.active_donor_count - ejected.length} active ·{" "}
              {ejected.length} ejected · click any donor to toggle
            </p>
            <div
              className="inline-flex items-center rounded-md border border-white/10 p-0.5"
              role="tablist"
              data-testid="view-toggle"
            >
              <ViewToggleButton
                active={view === "graph"}
                onClick={() => onViewChange("graph")}
                icon={Network}
                label="Graph"
                testid="view-toggle-graph"
              />
              <ViewToggleButton
                active={view === "grid"}
                onClick={() => onViewChange("grid")}
                icon={Grid3x3}
                label="Grid"
                testid="view-toggle-grid"
              />
            </div>
          </div>
        </div>

        {view === "graph" ? (
          <div
            className={cn("transition-opacity", pending && "opacity-70")}
          >
            <CohortGraph
              patientName={selectedBridge?.patient_name ?? outcome.bridge_name}
              patientBloodGroup={selectedBridge?.blood_group ?? "—"}
              cohort={outcome.baseline.cohort}
              ejectedSet={ejectedSet}
              onToggle={onToggleEject}
            />
          </div>
        ) : (
          <div
            className={cn(
              "grid grid-cols-1 gap-3 transition-opacity sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4",
              pending && "opacity-70",
            )}
          >
            {outcome.baseline.cohort.map((m) => (
              <DonorTile
                key={m.donor_id}
                member={m}
                ejected={ejectedSet.has(m.donor_id)}
                onClick={() => onToggleEject(m.donor_id)}
              />
            ))}
          </div>
        )}
      </section>

      {/* Replacement suggestions */}
      {outcome.scenario.top_candidates.length > 0 ? (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white">
              Suggested replacements
            </h2>
            <p className="text-xs text-white/40">
              Ranked by composite score · stability + distance + response + Kell-match
            </p>
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            {outcome.scenario.top_candidates.map((c) => (
              <div
                key={c.donor.id}
                className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4"
                data-testid="candidate-tile"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-medium text-white">{c.donor.name}</p>
                    <p className="text-xs text-white/50">
                      {c.donor.age} · {c.donor.city} ·{" "}
                      <span className="font-mono">{c.donor.blood_group}</span>
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-[11px] uppercase tracking-wider text-white/40">
                      Score
                    </p>
                    <p className="font-mono text-lg font-semibold text-emerald-300">
                      {Math.round(c.composite_score * 100)}
                    </p>
                  </div>
                </div>
                <div className="mt-2 grid grid-cols-3 gap-2 text-[11px] text-white/60">
                  <span>{c.distance_km.toFixed(1)} km</span>
                  <span>{Math.round(c.donor.response_rate * 100)}% resp</span>
                  <span>{Math.round(c.predicted_churn_90d * 100)}% churn</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <p className="mt-4 text-xs text-white/30">
        Solver ran in {outcome.scenario.schedule_solve_time_ms} ms · today{" "}
        {formatDate(outcome.today)} · model inference + scheduler + recommender end-to-end
      </p>
    </div>
  );
}

// Blood Bridge design target is 8-10 donors per cohort; below 5 is "critical"
// (matches the bridge.health threshold). Dropping below this floor
// is structurally bad regardless of which donors were ejected — a 2-donor
// cohort can't cover an 18-day transfusion cadence no matter how reliable
// those 2 donors are.
const MIN_VIABLE_COHORT = 5;

function DeltaBanner({ outcome }: { outcome: ScenarioOutcome }) {
  const { baseline, scenario, delta, requested } = outcome;
  const noChange = requested.ejected_donor_ids.length === 0;

  const churnPctBefore = Math.round(baseline.avg_churn_90d * 100);
  const churnPctAfter = Math.round(scenario.avg_churn_90d * 100);
  // A churn-only direction is misleading once headcount drops below viable —
  // ejecting the 2 worst donors from a 4-donor cohort lowers avg churn but
  // leaves the patient unschedulable. Headcount trumps churn here.
  const droppedBelowViable =
    scenario.active_donor_count < MIN_VIABLE_COHORT &&
    scenario.active_donor_count < baseline.active_donor_count;
  const churnDirection =
    delta.avg_churn_change < -0.005
      ? "down"
      : delta.avg_churn_change > 0.005
      ? "up"
      : "flat";
  const verdict: "improved" | "worsened" | "flat" | "unviable" = droppedBelowViable
    ? "unviable"
    : churnDirection === "down"
    ? "improved"
    : churnDirection === "up"
    ? "worsened"
    : "flat";
  const verdictPill = {
    improved: {
      cls: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
      label: "Health improved",
    },
    worsened: {
      cls: "border-red-500/40 bg-red-500/10 text-red-300",
      label: "Health worsened",
    },
    flat: {
      cls: "border-white/10 bg-white/5 text-white/40",
      label: "No change",
    },
    unviable: {
      cls: "border-red-500/40 bg-red-500/10 text-red-300",
      label: "Cohort below viable size",
    },
  }[verdict];

  return (
    <section className="rounded-xl border border-white/5 bg-surface/40 p-5" data-testid="delta-banner">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-white/40">
          {noChange ? "Baseline state" : "Scenario delta"}
        </h2>
        {!noChange ? (
          <span
            className={cn(
              "rounded-full border px-2 py-0.5 text-[11px] uppercase tracking-wider",
              verdictPill.cls,
            )}
            data-testid="churn-direction"
            data-verdict={verdict}
          >
            {verdictPill.label}
          </span>
        ) : null}
      </div>

      {droppedBelowViable ? (
        <div
          data-testid="cohort-unviable-warning"
          className="mb-3 rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-200/90"
        >
          <strong className="text-red-200">Cohort dropped to {scenario.active_donor_count} active donors</strong>{" "}
          — below the {MIN_VIABLE_COHORT}-donor minimum. Even if churn risk
          improved, the patient's transfusion cadence cannot be reliably
          covered. Recruit replacements before applying this scenario.
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <DeltaTile
          icon={Users}
          label="Cohort size"
          before={baseline.active_donor_count}
          after={scenario.active_donor_count}
          format={(n) => String(n)}
        />
        <DeltaTile
          icon={Brain}
          label="Avg 90d churn"
          before={churnPctBefore}
          after={churnPctAfter}
          format={(n) => `${n}%`}
          lowerBetter
        />
        <DeltaTile
          icon={AlertTriangle}
          label="At-risk donors"
          before={baseline.at_risk_count}
          after={scenario.at_risk_count}
          format={(n) => String(n)}
          lowerBetter
        />
        <DeltaTile
          icon={Clock}
          label="Scheduler"
          before={baseline.schedule_status}
          after={scenario.schedule_status}
          format={(v) => String(v)}
        />
      </div>
    </section>
  );
}

function DeltaTile<T>({
  icon: Icon,
  label,
  before,
  after,
  format,
  lowerBetter = false,
}: {
  icon: typeof Users;
  label: string;
  before: T;
  after: T;
  format: (val: T) => string;
  lowerBetter?: boolean;
}) {
  const changed = String(before) !== String(after);
  let tone: "ok" | "warn" | "neutral" = "neutral";
  if (changed && typeof before === "number" && typeof after === "number") {
    const better = lowerBetter ? (after as number) < (before as number) : (after as number) > (before as number);
    tone = better ? "ok" : "warn";
  }
  return (
    <div className="rounded-xl border border-white/5 bg-surface/30 p-3">
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-white/40">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <div className="mt-1.5 flex items-baseline gap-2 text-sm">
        <span className="text-white/40 tabular-nums">{format(before)}</span>
        <ArrowRight className="h-3 w-3 shrink-0 text-white/30" />
        <span
          className={cn(
            "text-lg font-semibold tabular-nums",
            tone === "ok" && "text-emerald-300",
            tone === "warn" && "text-amber-300",
            tone === "neutral" && "text-white",
          )}
        >
          {format(after)}
        </span>
      </div>
    </div>
  );
}

function DonorTile({
  member,
  ejected,
  onClick,
}: {
  member: CohortMemberState;
  ejected: boolean;
  onClick: () => void;
}) {
  const pct = Math.round(member.churn_90d * 100);
  const riskColor =
    pct >= 50 ? "text-red-300" : pct >= 25 ? "text-amber-300" : "text-emerald-300";
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid="donor-tile"
      data-ejected={ejected}
      className={cn(
        "rounded-xl border p-3 text-left transition-all",
        ejected
          ? "border-white/10 bg-black/40 opacity-60"
          : "border-white/10 bg-surface/40 hover:border-primary/40 hover:bg-surface/60",
      )}
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <p className={cn("font-medium", ejected ? "text-white/50 line-through" : "text-white")}>
              {member.donor_name}
            </p>
          </div>
          <p className="text-xs text-white/40">
            <span className="font-mono">{member.blood_group}</span>
          </p>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] uppercase tracking-wider",
            ejected
              ? "border-white/10 bg-white/5 text-white/40"
              : "border-red-500/40 bg-red-500/10 text-red-200",
          )}
        >
          {ejected ? (
            <>
              <Undo2 className="h-3 w-3" /> Restore
            </>
          ) : (
            <>
              <UserMinus className="h-3 w-3" /> Eject
            </>
          )}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-1.5 text-[11px]">
        <ChurnPill label="30d" value={Math.round(member.churn_30d * 100)} dim={ejected} />
        <ChurnPill label="60d" value={Math.round(member.churn_60d * 100)} dim={ejected} />
        <ChurnPill label="90d" value={pct} dim={ejected} bold />
      </div>
      {!ejected && pct >= 50 ? (
        <p className={cn("mt-2 flex items-center gap-1 text-[11px]", riskColor)}>
          <Zap className="h-3 w-3" /> High churn risk
        </p>
      ) : null}
    </button>
  );
}

function ChurnPill({
  label,
  value,
  dim,
  bold = false,
}: {
  label: string;
  value: number;
  dim?: boolean;
  bold?: boolean;
}) {
  const color =
    value >= 50 ? "text-red-300" : value >= 25 ? "text-amber-300" : "text-emerald-300";
  return (
    <span
      className={cn(
        "flex flex-col items-center rounded bg-white/5 px-1.5 py-1",
        dim && "opacity-40",
      )}
    >
      <span className="text-[10px] uppercase tracking-wider text-white/40">{label}</span>
      <span className={cn("tabular-nums", color, bold && "font-semibold")}>{value}%</span>
    </span>
  );
}

function SimulatorSkeleton() {
  return (
    <div className="space-y-6">
      <div className="h-28 animate-pulse rounded-xl border border-white/5 bg-surface/30" />
      <div className="grid grid-cols-4 gap-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-xl border border-white/5 bg-surface/30"
          />
        ))}
      </div>
    </div>
  );
}

function ViewToggleButton({
  active,
  onClick,
  icon: Icon,
  label,
  testid,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  testid: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      data-testid={testid}
      className={cn(
        "inline-flex items-center gap-1.5 rounded px-2 py-1 text-[11px] uppercase tracking-wider transition-colors",
        active
          ? "bg-primary/15 text-primary"
          : "text-white/50 hover:text-white",
      )}
    >
      <Icon className="h-3 w-3" />
      {label}
    </button>
  );
}
