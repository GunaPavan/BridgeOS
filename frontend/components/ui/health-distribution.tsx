import type { HealthCounts } from "@/lib/api";
import { cn } from "@/lib/utils";

const SEGMENT_STYLES = {
  stable: { color: "bg-emerald-500/80", label: "Stable", text: "text-emerald-300" },
  at_risk: { color: "bg-amber-500/80", label: "At risk", text: "text-amber-300" },
  critical: { color: "bg-red-500/80", label: "Critical", text: "text-red-300" },
} as const;

export function HealthDistribution({
  title,
  counts,
  className,
}: {
  title: string;
  counts: HealthCounts;
  className?: string;
}) {
  const total = counts.stable + counts.at_risk + counts.critical;
  const safe = Math.max(total, 1);
  const segments = (["stable", "at_risk", "critical"] as const).map((k) => ({
    key: k,
    pct: (counts[k] / safe) * 100,
    count: counts[k],
    style: SEGMENT_STYLES[k],
  }));

  return (
    <div
      className={cn("rounded-xl border border-white/5 bg-surface/40 p-4", className)}
      data-testid="health-distribution"
    >
      <div className="mb-2 flex items-end justify-between">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        <span className="text-xs text-white/40">{total} bridges</span>
      </div>

      {/* Stacked bar */}
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-white/5">
        {segments.map((s) =>
          s.pct > 0 ? (
            <div
              key={s.key}
              className={cn("h-full", s.style.color)}
              style={{ width: `${s.pct}%` }}
              title={`${s.style.label}: ${s.count} (${s.pct.toFixed(0)}%)`}
            />
          ) : null,
        )}
      </div>

      {/* Legend */}
      <div className="mt-3 grid grid-cols-3 gap-2">
        {segments.map((s) => (
          <div key={s.key} className="flex items-baseline gap-2">
            <span
              className={cn("h-2 w-2 shrink-0 rounded-full", s.style.color)}
              aria-hidden
            />
            <div>
              <p className={cn("text-base font-semibold tabular-nums", s.style.text)}>
                {s.count}
              </p>
              <p className="text-[11px] text-white/40">{s.style.label}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
