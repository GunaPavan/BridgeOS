"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  AlertOctagon,
  Clock,
  Loader2,
  Network,
  Play,
  RefreshCw,
  Sparkles,
  Zap,
} from "lucide-react";
import { useState } from "react";

import { SchedulerTick } from "@/components/ui/scheduler-tick";
import {
  api,
  type DonorListItem,
  type OutreachAllocation,
  type OutreachAllocationBatch,
  type OutreachWaveSummary,
} from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";

const STATUS_PILL: Record<string, string> = {
  active: "border-sky-400/40 bg-sky-500/15 text-sky-200",
  accepted: "border-emerald-400/40 bg-emerald-500/15 text-emerald-200",
  expired: "border-red-400/40 bg-red-500/15 text-red-200",
  cancelled: "border-white/15 bg-white/5 text-white/50",
};

const URGENCY_PILL: Record<string, string> = {
  critical: "border-red-500/40 bg-red-500/15 text-red-300",
  high: "border-amber-500/40 bg-amber-500/15 text-amber-300",
  medium: "border-blue-500/40 bg-blue-500/15 text-blue-300",
  planned: "border-white/10 bg-white/5 text-white/40",
};

export default function OutreachPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [previewOpen, setPreviewOpen] = useState(false);

  const [sweepResult, setSweepResult] = useState<{
    expired: number;
    escalated: number;
  } | null>(null);

  const wavesQ = useQuery({
    queryKey: ["outreach-waves", statusFilter],
    queryFn: () => api.listOutreachWaves({ status: statusFilter || undefined, limit: 200 }),
    refetchInterval: 20_000,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["outreach-waves"] });

  const expireSweep = useMutation({
    mutationFn: () => api.expireAndSweep(true),
    onSuccess: (r) => {
      setSweepResult({
        expired: (r as { expired_count?: number }).expired_count ?? 0,
        escalated:
          ((r as { escalated_waves?: string[] }).escalated_waves ?? []).length,
      });
      refresh();
      // Auto-clear the banner after 6s
      setTimeout(() => setSweepResult(null), 6000);
    },
  });

  return (
    <div className="px-8 py-8" data-testid="outreach-page">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Zap className="h-3.5 w-3.5" />
            Alert Allocator
          </div>
          <h1 className="mt-1 text-3xl font-bold text-white">Outreach waves</h1>
          <p className="mt-1 text-sm text-white/60">
            Coordinator control panel for the global donor outreach engine. Run
            cycles, dispatch waves, drive escalations.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <SchedulerTick job="auto_run_cycle" />
          <button
            type="button"
            onClick={() => expireSweep.mutate()}
            disabled={expireSweep.isPending}
            data-testid="expire-sweep-button"
            className="inline-flex items-center gap-2 rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-1.5 text-sm text-amber-200 hover:border-amber-300/60 hover:bg-amber-500/20 disabled:opacity-50"
          >
            <Clock className="h-3.5 w-3.5" />
            Expire + auto-escalate
          </button>
          <button
            type="button"
            onClick={() => setPreviewOpen(true)}
            data-testid="run-cycle-button"
            className="inline-flex items-center gap-2 rounded-lg border border-primary/40 bg-primary/15 px-3 py-1.5 text-sm font-semibold text-primary hover:border-primary/60 hover:bg-primary/25"
          >
            <Play className="h-3.5 w-3.5" />
            Run allocator cycle
          </button>
          <button
            type="button"
            onClick={refresh}
            className="rounded-md border border-white/10 px-2 py-1.5 text-xs text-white/60 hover:border-white/20"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", wavesQ.isFetching && "animate-spin")} />
          </button>
        </div>
      </header>

      {/* Expire-sweep result banner */}
      {sweepResult ? (
        <div
          data-testid="sweep-result-banner"
          className={cn(
            "mb-4 rounded-lg border px-4 py-2 text-sm",
            sweepResult.expired === 0
              ? "border-white/10 bg-white/5 text-white/60"
              : "border-emerald-400/30 bg-emerald-500/10 text-emerald-200",
          )}
        >
          {sweepResult.expired === 0 ? (
            <span>
              Nothing to expire — no ACTIVE waves had their{" "}
              <span className="font-mono">expires_at</span> in the past. Waves
              auto-expire 30 min after creation (critical) up to 12 h (medium);
              come back later or dispatch waves so they start the timer.
            </span>
          ) : (
            <span>
              Expired <span className="font-mono">{sweepResult.expired}</span>{" "}
              waves; auto-escalated{" "}
              <span className="font-mono">{sweepResult.escalated}</span> to the
              next tier. Refresh the list to see the new waves.
            </span>
          )}
        </div>
      ) : null}

      {/* Status filter chips */}
      <div className="mb-4 flex items-center gap-2" data-testid="status-filter">
        {(["", "active", "accepted", "expired", "cancelled"] as const).map((s) => (
          <button
            key={s || "all"}
            type="button"
            onClick={() => setStatusFilter(s)}
            data-testid={`status-chip-${s || "all"}`}
            className={cn(
              "rounded-full border px-3 py-1 text-xs uppercase tracking-wider",
              statusFilter === s
                ? "border-primary/50 bg-primary/15 text-primary"
                : "border-white/10 text-white/50 hover:border-white/20",
            )}
          >
            {s || "all"}
          </button>
        ))}
      </div>

      {/* Waves table */}
      {wavesQ.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="h-14 animate-pulse rounded-lg border border-white/5 bg-surface/30"
            />
          ))}
        </div>
      ) : wavesQ.data && wavesQ.data.items.length === 0 ? (
        <div
          className="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-white/40"
          data-testid="waves-empty"
        >
          No waves match this filter. Run an allocator cycle to create some.
        </div>
      ) : (
        <ul className="space-y-2" data-testid="waves-list">
          {wavesQ.data?.items.map((w) => (
            <WaveRow key={w.id} wave={w} />
          ))}
        </ul>
      )}

      {previewOpen ? (
        <RunCycleModal onClose={() => { setPreviewOpen(false); refresh(); }} />
      ) : null}
    </div>
  );
}

function WaveRow({ wave }: { wave: OutreachWaveSummary }) {
  const created = wave.created_at ? formatDate(wave.created_at) : "—";
  const expires = wave.expires_at ? new Date(wave.expires_at).toLocaleString() : "—";
  return (
    <li data-testid="wave-row" data-status={wave.status} data-urgency={wave.urgency}>
      <Link
        href={`/outreach/${wave.id}`}
        className="block rounded-lg border border-white/5 bg-surface/40 p-4 transition hover:border-white/15 hover:bg-surface/60"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-xs text-white/40">
              <Network className="h-3 w-3" />
              <span className="font-mono">{wave.tier.replace("_", " ")}</span>
              <span className="text-white/20">·</span>
              <span>{wave.triggered_by}</span>
            </div>
            <p className="mt-1 text-sm font-medium text-white">
              Slot {wave.slot_date} · gap {wave.gap_days_at_creation}d · pool{" "}
              {wave.pool_size_at_creation}
            </p>
            <p className="mt-0.5 text-xs text-white/40">
              created {created} · expires {expires}
            </p>
          </div>
          <div className="shrink-0 text-right text-xs">
            <div className="flex items-center justify-end gap-2">
              <span
                className={cn(
                  "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
                  URGENCY_PILL[wave.urgency] ?? URGENCY_PILL.medium,
                )}
                data-testid="urgency-pill"
              >
                {wave.urgency}
              </span>
              <span
                className={cn(
                  "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
                  STATUS_PILL[wave.status] ?? STATUS_PILL.cancelled,
                )}
                data-testid="status-pill"
              >
                {wave.status}
              </span>
            </div>
            <p className="mt-1 font-mono text-[11px] text-white/55">
              P_accept {(wave.realised_p_accept * 100).toFixed(0)}% /{" "}
              {(wave.target_p_accept * 100).toFixed(0)}%
            </p>
          </div>
        </div>
      </Link>
    </li>
  );
}

/** Per-allocation in-modal selection state — captures what coordinator
 *  toggled / edited before commit. Default: all rows selected, original
 *  donor batches. */
type EditState = Record<
  string, // allocation key: `${patient_id}__${slot_date}`
  {
    selected: boolean;
    donors: OutreachAllocationBatch[];
    expanded: boolean;
  }
>;

function allocKey(a: { patient_id: string; slot_date: string }): string {
  return `${a.patient_id}__${a.slot_date}`;
}

function RunCycleModal({ onClose }: { onClose: () => void }) {
  const [horizonDays, setHorizonDays] = useState(7);
  const [preview, setPreview] = useState<{
    summary: { open_slots: number; waves_created: number; pings_planned: number; critical_slots: number; high_slots: number; medium_slots: number };
    allocations: OutreachAllocation[];
  } | null>(null);
  const [edits, setEdits] = useState<EditState>({});
  const [error, setError] = useState<string | null>(null);
  const [commitResult, setCommitResult] = useState<{
    created_count: number;
    created_wave_ids: string[];
    diagnostics: Array<{ patient_id: string; skipped_reason?: string; wave_id?: string; dropped?: string[] }>;
  } | null>(null);

  const dryRun = useMutation({
    mutationFn: () => api.runOutreachCycle({ dryRun: true, horizonDays }),
    onSuccess: (r) => {
      setPreview(r);
      // Seed edits: every row selected by default (user can deselect what
      // they don't want, or add donors to empty batches and then commit).
      const seed: EditState = {};
      for (const a of r.allocations) {
        seed[allocKey(a)] = {
          selected: true,
          donors: [...a.batch],
          expanded: false,
        };
      }
      setEdits(seed);
    },
    onError: (e: Error) => setError(e.message),
  });

  const commit = useMutation({
    mutationFn: async () => {
      if (!preview) throw new Error("No preview to commit");
      const selections = preview.allocations
        .filter((a) => edits[allocKey(a)]?.selected && edits[allocKey(a)]?.donors.length > 0)
        .map((a) => ({
          patient_id: a.patient_id,
          slot_date: a.slot_date,
          donor_ids: edits[allocKey(a)].donors.map((d) => d.donor_id),
        }));
      if (selections.length === 0) {
        throw new Error("Select at least one allocation with donors.");
      }
      return api.commitAllocations(selections);
    },
    onSuccess: (r) => setCommitResult(r),
    onError: (e: Error) => setError(e.message),
  });

  const toggleSelected = (key: string) =>
    setEdits((e) => ({ ...e, [key]: { ...e[key], selected: !e[key]?.selected } }));
  const toggleExpanded = (key: string) =>
    setEdits((e) => ({ ...e, [key]: { ...e[key], expanded: !e[key]?.expanded } }));
  const removeDonor = (key: string, donorId: string) =>
    setEdits((e) => ({
      ...e,
      [key]: { ...e[key], donors: e[key].donors.filter((d) => d.donor_id !== donorId) },
    }));
  const addDonor = (key: string, donor: OutreachAllocationBatch) =>
    setEdits((e) => {
      if (e[key].donors.some((d) => d.donor_id === donor.donor_id)) return e;
      return { ...e, [key]: { ...e[key], donors: [...e[key].donors, donor] } };
    });

  const selectAll = () =>
    setEdits((e) => {
      // Select every row — including empty-batch ones, so the user can expand
      // and add donors. Commit safely skips selected rows that still end up
      // with zero donors at submit time.
      const next: EditState = {};
      for (const [k, v] of Object.entries(e)) next[k] = { ...v, selected: true };
      return next;
    });
  const selectNone = () =>
    setEdits((e) => {
      const next: EditState = {};
      for (const [k, v] of Object.entries(e)) next[k] = { ...v, selected: false };
      return next;
    });

  // Count rows the user has checked (regardless of donor count) — drives the
  // visible "N selected" label so users see immediate feedback on every click.
  const selectedCount = preview
    ? preview.allocations.filter((a) => edits[allocKey(a)]?.selected).length
    : 0;
  // Count rows that will actually create a wave (checked AND donors > 0) —
  // drives the commit button disabled state + the "M will commit" caption.
  const commitableCount = preview
    ? preview.allocations.filter(
        (a) => edits[allocKey(a)]?.selected && (edits[allocKey(a)]?.donors.length ?? 0) > 0,
      ).length
    : 0;
  const totalPings = preview
    ? preview.allocations
        .filter((a) => edits[allocKey(a)]?.selected)
        .reduce((sum, a) => sum + (edits[allocKey(a)]?.donors.length ?? 0), 0)
    : 0;
  const emptyBatchSelectedCount = selectedCount - commitableCount;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      data-testid="run-cycle-modal"
    >
      <div className="mx-4 max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-primary/30 bg-surface p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <h2 className="text-lg font-semibold text-white">Allocator cycle preview</h2>
          </div>
          <button onClick={onClose} className="text-white/40 hover:text-white" data-testid="close-modal">
            ✕
          </button>
        </div>

        {!preview && !commitResult ? (
          <div className="space-y-3">
            <div>
              <label className="text-xs uppercase tracking-wider text-white/40">
                Horizon (days)
              </label>
              <input
                type="number"
                min={1}
                max={30}
                value={horizonDays}
                onChange={(e) => setHorizonDays(Number(e.target.value) || 7)}
                data-testid="horizon-input"
                className="mt-1 w-32 rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-white"
              />
            </div>
            <button
              type="button"
              onClick={() => dryRun.mutate()}
              disabled={dryRun.isPending}
              data-testid="dry-run-button"
              className="w-full rounded-lg border border-primary/50 bg-primary/20 py-3 text-sm font-semibold text-primary hover:bg-primary/30 disabled:opacity-50"
            >
              {dryRun.isPending ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 className="h-3 w-3 animate-spin" /> Computing allocation…
                </span>
              ) : (
                "Preview proposed waves"
              )}
            </button>
            {error ? <p className="text-xs text-red-300">{error}</p> : null}
          </div>
        ) : commitResult ? (
          <div data-testid="commit-result" className="space-y-3">
            <div className="rounded-lg border border-emerald-400/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">
              <p className="font-semibold">Committed {commitResult.created_count} waves</p>
              <p className="mt-1 text-xs text-emerald-200/80">
                Each wave is now ACTIVE on /outreach — dispatch them from there
                to send the WhatsApps.
              </p>
            </div>
            {commitResult.diagnostics.some((d) => d.skipped_reason || d.dropped?.length) ? (
              <details className="text-xs">
                <summary className="cursor-pointer text-white/60">
                  Show diagnostics ({commitResult.diagnostics.length})
                </summary>
                <pre className="mt-1 whitespace-pre-wrap text-[10px] text-white/50">
                  {JSON.stringify(commitResult.diagnostics, null, 2)}
                </pre>
              </details>
            ) : null}
            <button
              onClick={onClose}
              className="w-full rounded-md border border-white/10 bg-white/5 py-2 text-sm text-white/80 hover:bg-white/10"
            >
              Close
            </button>
          </div>
        ) : preview ? (
          <div data-testid="cycle-preview">
            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <Stat label="Slots" value={preview.summary.open_slots} />
              <Stat label="Waves proposed" value={preview.summary.waves_created} />
              <Stat label="Pings proposed" value={preview.summary.pings_planned} />
              <Stat label="Critical" value={preview.summary.critical_slots} tone="red" />
              <Stat label="High" value={preview.summary.high_slots} tone="amber" />
              <Stat label="Medium" value={preview.summary.medium_slots} tone="sky" />
            </div>

            <div className="mt-3 flex items-center justify-between text-[11px] text-white/40">
              <span data-testid="selection-counter">
                <span className="font-mono text-white">{selectedCount}</span>{" "}
                selected ·{" "}
                <span className="font-mono text-emerald-300" data-testid="commitable-count">
                  {commitableCount}
                </span>{" "}
                ready · <span className="font-mono text-white">{totalPings}</span> pings
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={selectAll}
                  data-testid="select-all-button"
                  className="rounded border border-white/10 px-2 py-0.5 text-[10px] text-white/60 hover:text-white"
                >
                  Select all
                </button>
                <button
                  onClick={selectNone}
                  data-testid="select-none-button"
                  className="rounded border border-white/10 px-2 py-0.5 text-[10px] text-white/60 hover:text-white"
                >
                  Select none
                </button>
              </div>
            </div>

            {emptyBatchSelectedCount > 0 ? (
              <div
                className="mt-2 rounded-md border border-amber-400/30 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-200"
                data-testid="empty-batch-hint"
              >
                {emptyBatchSelectedCount} selected{" "}
                {emptyBatchSelectedCount === 1 ? "row has" : "rows have"} no donors
                — expand to add some, or those will be skipped on commit.
              </div>
            ) : null}

            <ul
              className="mt-3 max-h-96 space-y-1 overflow-y-auto rounded-md border border-white/10 bg-black/20 p-1"
              data-testid="cycle-allocations-list"
            >
              {preview.allocations.map((a) => {
                const key = allocKey(a);
                const edit = edits[key];
                if (!edit) return null;
                return (
                  <AllocationEditor
                    key={key}
                    allocation={a}
                    edit={edit}
                    onToggleSelected={() => toggleSelected(key)}
                    onToggleExpanded={() => toggleExpanded(key)}
                    onRemoveDonor={(did) => removeDonor(key, did)}
                    onAddDonor={(d) => addDonor(key, d)}
                  />
                );
              })}
            </ul>

            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => { setPreview(null); setEdits({}); }}
                className="rounded-md border border-white/10 px-3 py-1.5 text-xs text-white/60 hover:border-white/20"
              >
                Back
              </button>
              <button
                type="button"
                onClick={() => commit.mutate()}
                disabled={commit.isPending || commitableCount === 0}
                data-testid="commit-cycle"
                title={
                  commitableCount === 0 && selectedCount > 0
                    ? "Selected rows have no donors — add some inside each row before committing."
                    : ""
                }
                className="rounded-md border border-emerald-400/50 bg-emerald-500/20 px-4 py-1.5 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/30 disabled:opacity-40"
              >
                {commit.isPending
                  ? "Persisting…"
                  : `Commit selected (${selectedCount}${
                      selectedCount !== commitableCount ? ` · ${commitableCount} ready` : ""
                    })`}
              </button>
            </div>
            {error ? <p className="mt-2 text-xs text-red-300">{error}</p> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function AllocationEditor({
  allocation,
  edit,
  onToggleSelected,
  onToggleExpanded,
  onRemoveDonor,
  onAddDonor,
}: {
  allocation: OutreachAllocation;
  edit: { selected: boolean; donors: OutreachAllocationBatch[]; expanded: boolean };
  onToggleSelected: () => void;
  onToggleExpanded: () => void;
  onRemoveDonor: (donorId: string) => void;
  onAddDonor: (d: OutreachAllocationBatch) => void;
}) {
  const [searchQ, setSearchQ] = useState("");
  const searchResults = useQuery({
    queryKey: ["donor-search", searchQ, allocation.patient_id],
    queryFn: () => api.listDonors({
      search: searchQ,
      limit: 10,
      is_active: true,
    }),
    enabled: edit.expanded && searchQ.trim().length >= 2,
  });

  return (
    <li
      data-testid="allocation-row"
      data-patient-id={allocation.patient_id}
      data-selected={edit.selected}
      className={cn(
        "rounded-md border p-2",
        edit.selected
          ? "border-primary/30 bg-primary/5"
          : "border-white/5 bg-black/10 opacity-60",
      )}
    >
      <div className="flex items-center gap-2 text-xs">
        <input
          type="checkbox"
          checked={edit.selected}
          onChange={onToggleSelected}
          data-testid="allocation-checkbox"
          className="h-3.5 w-3.5 accent-primary"
        />
        <button
          type="button"
          onClick={onToggleExpanded}
          data-testid="allocation-expand"
          className="flex flex-1 items-center justify-between gap-2 text-left hover:text-white"
        >
          <span className="truncate">
            <span className="font-medium text-white">{allocation.patient_name}</span>
            <span className="ml-2 text-white/40">{allocation.slot_date}</span>
          </span>
          <span className="flex items-center gap-2 shrink-0 text-white/55">
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
                URGENCY_PILL[allocation.urgency] ?? URGENCY_PILL.medium,
              )}
            >
              {allocation.urgency}
            </span>
            <span className="font-mono">
              {edit.donors.length} donor{edit.donors.length === 1 ? "" : "s"} ·{" "}
              {(allocation.realised_p_accept * 100).toFixed(0)}%
            </span>
            <span className="text-white/30">{edit.expanded ? "▾" : "▸"}</span>
          </span>
        </button>
      </div>

      {edit.expanded ? (
        <div className="mt-2 space-y-2 pl-6" data-testid="allocation-editor">
          {/* Donor pills */}
          <div className="flex flex-wrap gap-1.5">
            {edit.donors.length === 0 ? (
              <span className="text-[11px] text-amber-300">
                No donors in this batch — add one below or deselect this allocation.
              </span>
            ) : (
              edit.donors.map((d) => (
                <span
                  key={d.donor_id}
                  data-testid="batch-donor-pill"
                  className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-white/80"
                >
                  {d.donor_name}{" "}
                  <span className="font-mono text-white/40">{d.blood_group}</span>
                  <button
                    type="button"
                    onClick={() => onRemoveDonor(d.donor_id)}
                    data-testid="remove-donor-button"
                    aria-label={`Remove ${d.donor_name}`}
                    className="rounded-full p-0.5 text-white/40 hover:bg-red-500/20 hover:text-red-300"
                  >
                    ×
                  </button>
                </span>
              ))
            )}
          </div>

          {/* Add donor search */}
          <div>
            <input
              type="text"
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
              placeholder="Search a donor to add… (min 2 chars)"
              data-testid="add-donor-search"
              className="w-full rounded border border-white/10 bg-black/30 px-2 py-1 text-[11px] text-white/80 placeholder:text-white/30"
            />
            {searchQ.trim().length >= 2 && searchResults.data?.items ? (
              <ul
                className="mt-1 max-h-32 overflow-y-auto rounded border border-white/5 bg-black/40"
                data-testid="donor-search-results"
              >
                {searchResults.data.items.length === 0 ? (
                  <li className="px-2 py-1 text-[10px] text-white/40">No matches</li>
                ) : (
                  searchResults.data.items.map((d) => {
                    const alreadyIn = edit.donors.some((x) => x.donor_id === d.id);
                    return (
                      <li key={d.id}>
                        <button
                          type="button"
                          disabled={alreadyIn}
                          onClick={() => {
                            onAddDonor({
                              donor_id: d.id,
                              donor_name: d.name,
                              blood_group: d.blood_group,
                              city: d.city,
                              preferred_language: d.preferred_language,
                            });
                            setSearchQ("");
                          }}
                          data-testid="donor-search-result"
                          className="flex w-full items-center justify-between px-2 py-1 text-left text-[11px] text-white/80 hover:bg-white/5 disabled:opacity-40"
                        >
                          <span>{d.name}</span>
                          <span className="font-mono text-white/40">{d.blood_group} · {d.city}</span>
                        </button>
                      </li>
                    );
                  })
                )}
              </ul>
            ) : null}
          </div>
        </div>
      ) : null}
    </li>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "red" | "amber" | "sky" }) {
  const toneClass = {
    red: "text-red-300",
    amber: "text-amber-300",
    sky: "text-sky-300",
  }[tone ?? "sky"];
  return (
    <div className="rounded-md border border-white/5 bg-black/20 p-2">
      <p className={cn("font-mono text-xl", tone ? toneClass : "text-white")}>{value}</p>
      <p className="text-[10px] uppercase tracking-wider text-white/40">{label}</p>
    </div>
  );
}
