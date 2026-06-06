import { cn } from "@/lib/utils";

/**
 * Simple horizontal bar list — for blood-group, city, or any
 * "label + count" breakdown. Bars are scaled to the max.
 */
export function BarList({
  title,
  items,
  total,
  className,
  mono = false,
  testId,
}: {
  title: string;
  items: { label: string; count: number }[];
  total?: number;
  className?: string;
  mono?: boolean;
  testId?: string;
}) {
  const max = Math.max(1, ...items.map((i) => i.count));

  return (
    <div
      className={cn("rounded-xl border border-white/5 bg-surface/40 p-4", className)}
      data-testid={testId ?? "bar-list"}
    >
      <div className="mb-3 flex items-end justify-between">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        {total !== undefined ? (
          <span className="text-xs text-white/40">{total} total</span>
        ) : null}
      </div>
      <div className="space-y-2">
        {items.map((item) => {
          const pct = (item.count / max) * 100;
          return (
            <div key={item.label} className="flex items-center gap-2 text-xs">
              <span
                className={cn(
                  "w-24 shrink-0 truncate text-white/70",
                  mono && "font-mono",
                )}
                title={item.label}
              >
                {item.label}
              </span>
              <div className="relative h-2 flex-1 rounded-full bg-white/5">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-primary/60 to-accent/60"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="w-10 shrink-0 text-right tabular-nums text-white">
                {item.count}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
