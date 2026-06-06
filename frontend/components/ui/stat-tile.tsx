import type { ComponentType, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function StatTile({
  icon: Icon,
  label,
  value,
  hint,
  tone = "default",
  className,
}: {
  icon?: ComponentType<{ className?: string }>;
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "primary" | "accent" | "warn" | "danger";
  className?: string;
}) {
  const valueClass = {
    default: "text-white",
    primary: "text-primary",
    accent: "text-accent",
    warn: "text-amber-300",
    danger: "text-red-300",
  }[tone];

  return (
    <div
      className={cn(
        "rounded-xl border border-white/5 bg-surface/40 p-4",
        className,
      )}
      data-testid="stat-tile"
    >
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-white/40">
        {Icon ? <Icon className="h-3 w-3" /> : null}
        {label}
      </div>
      <div className={cn("mt-1.5 text-2xl font-semibold tabular-nums", valueClass)}>
        {value}
      </div>
      {hint ? <p className="mt-0.5 text-[11px] text-white/40">{hint}</p> : null}
    </div>
  );
}
