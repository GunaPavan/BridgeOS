"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Network, RefreshCw } from "lucide-react";

import { BridgeCard } from "@/components/ui/bridge-card";
import { api } from "@/lib/api";

export default function BridgesPage() {
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["bridges", { limit: 100 }],
    queryFn: () => api.listBridges({ limit: 100 }),
  });

  return (
    <div className="px-8 py-8">
      <header className="mb-8 flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Network className="h-3.5 w-3.5" />
            Bridges
          </div>
          <h1 className="mt-1 text-3xl font-bold text-white">
            All Blood Bridges
          </h1>
          <p className="mt-1 text-sm text-white/60">
            {data
              ? `${data.total} active cohorts across the network. Click any bridge for the cohort timeline.`
              : "Loading cohorts…"}
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-white/70 hover:border-white/20 hover:text-white disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </header>

      {isLoading ? <BridgesSkeleton /> : null}

      {error ? (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" />
            Could not load bridges.
          </div>
          <p className="mt-1 text-red-300/80">
            Make sure the backend is running at{" "}
            <code className="rounded bg-black/30 px-1">http://localhost:8000</code>. ({error.message})
          </p>
        </div>
      ) : null}

      {data ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {data.items.map((bridge) => (
            <BridgeCard key={bridge.id} bridge={bridge} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function BridgesSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          className="h-40 animate-pulse rounded-xl border border-white/5 bg-surface/30"
        />
      ))}
    </div>
  );
}
