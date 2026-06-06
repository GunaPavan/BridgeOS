"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Trophy } from "lucide-react";
import { useState } from "react";

import { api, type MlBakeoffRow } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Bake-off table — shows every algorithm tested for the chosen model with the
 * metrics that informed the Borda multi-criteria ranking.
 *
 *   churn   → 10 algorithms, ranked by CV F1 / test F1 / AUC / latency
 *   survival → 7 algorithms, ranked by test C-index / latency / overfit gap
 */
export function BakeoffTable({
  model,
}: {
  model: "churn" | "survival";
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["ml-bakeoff", model],
    queryFn: () => api.getMlBakeoff(model),
    staleTime: 60_000,
  });

  const [showAll, setShowAll] = useState(false);

  if (isLoading) {
    return (
      <div
        data-testid={`bakeoff-table-loading-${model}`}
        className="rounded-xl border border-white/5 bg-surface/40 p-5"
      >
        <div className="h-32 animate-pulse rounded-lg bg-white/5" />
      </div>
    );
  }

  if (!data || data.rows.length === 0) return null;

  const rows = showAll ? data.rows : data.rows.slice(0, 5);

  return (
    <section
      data-testid={`bakeoff-table-${model}`}
      className="rounded-xl border border-white/5 bg-surface/40 p-5"
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-white/40">
            {model === "churn" ? "Churn classifier" : "Survival model"}{" "}
            bake-off
          </h3>
          <p className="mt-0.5 text-[11px] text-white/40">
            {data.n_algorithms_tested} algorithms tested · Winner:{" "}
            <span className="font-mono text-emerald-300">{data.winner}</span>
          </p>
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-white/5 bg-black/20">
        <table
          data-testid={`bakeoff-table-rows-${model}`}
          className="min-w-full text-xs"
        >
          <thead className="border-b border-white/5 text-[10px] uppercase tracking-wider text-white/40">
            <tr>
              <th className="px-3 py-2 text-left">Algorithm</th>
              {model === "churn" ? (
                <>
                  <th className="px-3 py-2 text-right">CV F1</th>
                  <th className="px-3 py-2 text-right">Test F1</th>
                  <th className="px-3 py-2 text-right">AUC</th>
                  <th className="px-3 py-2 text-right">Inf (ms)</th>
                </>
              ) : (
                <>
                  <th className="px-3 py-2 text-right">C-test</th>
                  <th className="px-3 py-2 text-right">C-train</th>
                  <th className="px-3 py-2 text-right">Inf (ms)</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, idx) => (
              <BakeoffRow
                key={r.name}
                row={r}
                model={model}
                isWinner={r.name === data.winner}
                showTopBadge={idx === 0}
              />
            ))}
          </tbody>
        </table>
      </div>

      {data.rows.length > 5 ? (
        <button
          type="button"
          data-testid={`bakeoff-show-all-${model}`}
          onClick={() => setShowAll((v) => !v)}
          className="mt-3 inline-flex items-center gap-1 text-xs text-white/60 hover:text-white"
        >
          <ChevronDown
            className={cn(
              "h-3 w-3 transition-transform",
              showAll ? "rotate-180" : "",
            )}
          />
          {showAll
            ? "Show top 5 only"
            : `Show all ${data.rows.length} algorithms`}
        </button>
      ) : null}
    </section>
  );
}

function BakeoffRow({
  row,
  model,
  isWinner,
  showTopBadge,
}: {
  row: MlBakeoffRow;
  model: "churn" | "survival";
  isWinner: boolean;
  showTopBadge: boolean;
}) {
  const failed = row.failed === true;
  const fmt = (n: number | undefined) =>
    typeof n === "number" ? n.toFixed(3) : "—";
  const fmtMs = (us: number | undefined) =>
    typeof us === "number" ? (us / 1000).toFixed(2) : "—";

  return (
    <tr
      data-testid={`bakeoff-row-${row.name}`}
      data-winner={isWinner}
      className={cn(
        "border-b border-white/5 last:border-b-0",
        isWinner ? "bg-emerald-500/5" : "",
        failed ? "opacity-50" : "",
      )}
    >
      <td className="flex items-center gap-1.5 px-3 py-2 font-mono text-white/90">
        {showTopBadge ? (
          <Trophy
            data-testid="bakeoff-winner-badge"
            className="h-3 w-3 text-emerald-300"
          />
        ) : null}
        {row.name}
        {failed ? (
          <span className="text-[10px] uppercase text-amber-300">failed</span>
        ) : null}
      </td>
      {model === "churn" ? (
        <>
          <td className="px-3 py-2 text-right tabular-nums text-white/80">
            {fmt(row.cv_macro_f1_mean)}
          </td>
          <td className="px-3 py-2 text-right tabular-nums text-white/80">
            {fmt(row.test_macro_f1)}
          </td>
          <td className="px-3 py-2 text-right tabular-nums text-white/80">
            {fmt(row.test_binary_auc)}
          </td>
          <td className="px-3 py-2 text-right tabular-nums text-white/60">
            {fmtMs(row.inference_time_us)}
          </td>
        </>
      ) : (
        <>
          <td className="px-3 py-2 text-right tabular-nums text-white/80">
            {fmt(row.c_index_test)}
          </td>
          <td className="px-3 py-2 text-right tabular-nums text-white/60">
            {fmt(row.c_index_train)}
          </td>
          <td className="px-3 py-2 text-right tabular-nums text-white/60">
            {fmtMs(row.inference_time_us)}
          </td>
        </>
      )}
    </tr>
  );
}
