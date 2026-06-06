import { cn } from "@/lib/utils";
import type { BridgeHealth } from "@/lib/api";

const VARIANTS: Record<BridgeHealth, { label: string; classes: string; dot: string }> = {
  stable: {
    label: "Stable",
    classes: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
    dot: "bg-emerald-400",
  },
  at_risk: {
    label: "At risk",
    classes: "border-amber-500/30 bg-amber-500/10 text-amber-300",
    dot: "bg-amber-400",
  },
  critical: {
    label: "Critical",
    classes: "border-red-500/30 bg-red-500/10 text-red-300",
    dot: "bg-red-400",
  },
};

export function HealthBadge({
  health,
  className,
}: {
  health: BridgeHealth;
  className?: string;
}) {
  const variant = VARIANTS[health];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        variant.classes,
        className,
      )}
      data-testid="health-badge"
      data-health={health}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", variant.dot)} aria-hidden />
      {variant.label}
    </span>
  );
}
