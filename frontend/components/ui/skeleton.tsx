import { cn } from "@/lib/utils";

/**
 * Skeleton block with a horizontal shimmer animation.
 * Drop in anywhere a value is loading — replaces ad-hoc Loader2 spinners.
 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      data-testid="skeleton"
      className={cn(
        "relative overflow-hidden rounded-md bg-white/5",
        "before:absolute before:inset-0 before:-translate-x-full",
        "before:animate-[shimmer_1.4s_infinite]",
        "before:bg-gradient-to-r before:from-transparent before:via-white/10 before:to-transparent",
        className,
      )}
    />
  );
}

/** A row of three stacked skeleton bars — useful as a list-item placeholder. */
export function SkeletonRow({ className }: { className?: string }) {
  return (
    <div className={cn("space-y-2", className)} data-testid="skeleton-row">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-3 w-2/3" />
      <Skeleton className="h-3 w-1/2" />
    </div>
  );
}
