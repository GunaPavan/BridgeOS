"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Brain,
  Building2,
  Clock,
  Droplet,
  Network,
  RefreshCw,
  ShieldCheck,
  Users,
  UserCircle2,
} from "lucide-react";

import { AnimatedCounter } from "@/components/ui/animated-counter";
import { BakeoffTable } from "@/components/ui/bakeoff-table";
import { BarList } from "@/components/ui/bar-list";
import { HealthDistribution } from "@/components/ui/health-distribution";
import { MLInsightsPanel } from "@/components/ui/ml-insights-panel";
import { MLStackOverview } from "@/components/ui/ml-stack-overview";
import { EmailChannelPanel } from "@/components/ui/email-channel-panel";
import { OutreachAnalyticsPanel } from "@/components/ui/outreach-analytics-panel";
import { ReplyIntelligencePanel } from "@/components/ui/reply-intelligence-panel";
import { StatTile } from "@/components/ui/stat-tile";
import { api } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";

export default function AnalyticsPage() {
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["analytics"],
    queryFn: () => api.getAnalytics(),
  });

  return (
    <div className="px-8 py-8">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Activity className="h-3.5 w-3.5" />
            Analytics
          </div>
          <h1 className="mt-1 text-3xl font-bold text-white">Network overview</h1>
          <p className="mt-1 text-sm text-white/60">
            {data
              ? `Generated ${new Date(data.generated_at).toLocaleString()} · ML stack scored every bridge in ${data.stability_compute_time_ms} ms`
              : "Loading analytics…"}
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-white/70 hover:border-white/20 hover:text-white disabled:opacity-50"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
          Refresh
        </button>
      </header>

      {isLoading ? <AnalyticsSkeleton /> : null}

      {error ? (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" />
            Could not load analytics.
          </div>
          <p className="mt-1 text-red-300/80">{error.message}</p>
        </div>
      ) : null}

      {data ? (
        <div className="space-y-6" data-testid="analytics-content">
          {/* --- Top totals row --- */}
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile
              icon={UserCircle2}
              label="Patients"
              value={<AnimatedCounter value={data.total_patients} />}
              hint="Active thalassemia care"
              tone="primary"
            />
            <StatTile
              icon={Users}
              label="Donors"
              value={<AnimatedCounter value={data.total_donors} />}
              hint={`${data.donor_pool.active} currently active`}
              tone="accent"
            />
            <StatTile
              icon={Network}
              label="Bridges"
              value={<AnimatedCounter value={data.cohort_stats.total_bridges} />}
              hint={`avg ${data.cohort_stats.avg_active_donors.toFixed(1)} active donors`}
            />
            <StatTile
              icon={Droplet}
              label="Active memberships"
              value={<AnimatedCounter value={data.cohort_stats.total_active_memberships} />}
            />
          </section>

          {/* --- ML-scored cohort health (single source of truth) --- */}
          <section>
            <HealthDistribution
              title="Cohort health"
              counts={data.cohort_stats.ml_health}
            />
          </section>

          {/* --- Alert Allocator operational analytics --- */}
          <OutreachAnalyticsPanel />

          {/* --- Reply intelligence (Bedrock classifier audit + analytics) --- */}
          <ReplyIntelligencePanel />

          {/* --- Email channel (SES) --- */}
          <EmailChannelPanel />

          {/* --- ML-driven network insights (live scoring of donor pool) --- */}
          <MLInsightsPanel />

          {/* --- Production ML stack (real-data churn + survival) --- */}
          <MLStackOverview />

          {/* --- Bake-off comparisons (expandable) --- */}
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <BakeoffTable model="churn" />
            <BakeoffTable model="survival" />
          </section>

          {/* --- Donor pool + city distribution --- */}
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <BarList
              title="Donor pool by blood group"
              total={data.donor_pool.total}
              items={data.donor_pool.by_blood_group.map((b) => ({
                label: b.blood_group,
                count: b.count,
              }))}
              mono
              testId="bg-chart"
            />
            <BarList
              title="Patients by city"
              total={data.total_patients}
              items={data.patients_by_city.map((c) => ({
                label: c.city,
                count: c.count,
              }))}
              testId="city-chart"
            />
          </section>

          {/* --- Donor pool stat row --- */}
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile
              icon={Users}
              label="Donors total"
              value={data.donor_pool.total}
            />
            <StatTile
              icon={Activity}
              label="Currently active"
              value={data.donor_pool.active}
              hint={`${Math.round((data.donor_pool.active / data.donor_pool.total) * 100)}% of pool`}
              tone="accent"
            />
            <StatTile
              icon={Building2}
              label="Eligible to donate now"
              value={data.donor_pool.eligible_now}
              hint="Active and past 90-day deferral"
              tone="primary"
            />
            <StatTile
              icon={ShieldCheck}
              label="Kell-negative donors"
              value={data.donor_pool.kell_negative}
              hint={`${Math.round((data.donor_pool.kell_negative / data.donor_pool.total) * 100)}% of pool`}
            />
          </section>
        </div>
      ) : null}
    </div>
  );
}

function AnalyticsSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-24 animate-pulse rounded-xl border border-white/5 bg-surface/30"
          />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="h-44 animate-pulse rounded-xl border border-white/5 bg-surface/30" />
        <div className="h-44 animate-pulse rounded-xl border border-white/5 bg-surface/30" />
      </div>
      <div className="h-56 animate-pulse rounded-xl border border-white/5 bg-surface/30" />
    </div>
  );
}
