"use client";

import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";

import { api } from "@/lib/api";

/**
 * Sticky red banner that hangs across the top of every authenticated page
 * when the scheduler is in demo mode. Polls /system/scheduler/status every
 * 30 seconds — when the toggle flips off the banner disappears within one
 * poll cycle without a page refresh.
 */
export function DemoModeBanner() {
  const { data } = useQuery({
    queryKey: ["scheduler-status"],
    queryFn: () => api.getSchedulerStatus(),
    refetchInterval: 30_000,
  });

  if (!data?.demo_mode) return null;

  return (
    <div
      data-testid="demo-mode-banner"
      className="sticky top-0 z-50 flex items-center justify-center gap-2 border-b border-red-500/40 bg-red-500/15 px-4 py-1.5 text-xs text-red-200"
    >
      <Sparkles className="h-3 w-3" />
      <span className="font-semibold uppercase tracking-wider">Demo mode ON</span>
      <span className="text-red-200/80">
        — cadences compressed. Real cadences resume when you exit demo mode.
      </span>
    </div>
  );
}
