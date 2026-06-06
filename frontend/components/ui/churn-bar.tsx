import { cn } from "@/lib/utils";

/**
 * Horizontal bar visualising a donor's churn probability for one horizon.
 * Color goes green -> amber -> red as risk rises.
 */
export function ChurnBar({
  value,
  label,
  className,
}: {
  value: number; // 0..1
  label: string;
  className?: string;
}) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const color =
    pct >= 50 ? "bg-red-500" : pct >= 25 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className={cn("flex items-center gap-2 text-xs", className)} data-testid="churn-bar">
      <span className="w-8 shrink-0 text-white/40">{label}</span>
      <div className="relative h-1.5 flex-1 rounded-full bg-white/10">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={cn("w-9 shrink-0 text-right tabular-nums", pct >= 50 && "text-red-300")}>
        {pct}%
      </span>
    </div>
  );
}
