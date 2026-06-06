"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Calendar,
  Clock,
  Droplet,
  Globe,
  Languages,
  MapPin,
  Phone,
  ShieldCheck,
  Zap,
} from "lucide-react";

import { ChurnPredictionCard } from "@/components/ui/churn-prediction-card";
import { ResponseTrend } from "@/components/ui/response-trend";
import { SurvivalCurve } from "@/components/ui/survival-curve";
import { api } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";

const LANGUAGE_LABEL: Record<string, string> = {
  en: "English",
  hi: "Hindi",
  te: "Telugu",
  ta: "Tamil",
  mr: "Marathi",
  bn: "Bengali",
  kn: "Kannada",
  gu: "Gujarati",
};

export default function DonorDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;

  const { data, isLoading, error } = useQuery({
    queryKey: ["donor", id],
    queryFn: () => api.getDonor(id as string),
    enabled: Boolean(id),
  });

  if (isLoading) {
    return (
      <div className="px-8 py-8">
        <div className="h-8 w-64 animate-pulse rounded bg-surface/40" />
        <div className="mt-6 h-48 animate-pulse rounded-xl bg-surface/40" />
        <div className="mt-4 h-64 animate-pulse rounded-xl bg-surface/40" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="px-8 py-8">
        <Link
          href="/donors"
          className="inline-flex items-center gap-2 text-sm text-white/70 hover:text-white"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to donors
        </Link>
        <p className="mt-6 text-red-300">
          Could not load this donor. {error?.message ?? "Unknown error."}
        </p>
      </div>
    );
  }

  const responsePct = Math.round(data.response_rate * 100);

  return (
    <div className="px-8 py-8">
      <Link
        href="/donors"
        className="inline-flex items-center gap-2 text-sm text-white/60 hover:text-white"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to donors
      </Link>

      {/* --- Header --- */}
      <header className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-3xl font-bold text-white">{data.name}</h1>
            {data.kell_negative ? (
              <ShieldCheck
                className="h-5 w-5 text-accent"
                aria-label="Kell-negative donor"
              />
            ) : null}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-white/70">
            <span
              className={cn(
                "rounded-md bg-white/5 px-2 py-0.5 font-mono",
                data.blood_group.endsWith("-") ? "text-accent" : "text-primary",
              )}
            >
              {data.blood_group}
            </span>
            <span>{data.age} years old</span>
            <span className="text-white/30">·</span>
            <MapPin className="h-3.5 w-3.5" /> {data.city}, {data.state}
          </div>
        </div>
        <span
          className={cn(
            "rounded-full px-3 py-1 text-xs uppercase tracking-wider",
            data.is_eligible_to_donate
              ? "bg-emerald-500/15 text-emerald-300"
              : "bg-amber-500/15 text-amber-300",
          )}
        >
          {data.is_eligible_to_donate ? "Eligible to donate" : "In cooldown"}
        </span>
      </header>

      {/* --- Stats --- */}
      <section className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard icon={Droplet} label="Total donations" value={String(data.total_donations)} />
        <StatCard
          icon={Calendar}
          label="Last donation"
          value={formatDate(data.last_donation_date)}
        />
        <StatCard icon={Zap} label="Response rate" value={`${responsePct}%`} />
        <StatCard
          icon={Clock}
          label="Avg response"
          value={`${data.avg_response_hours.toFixed(1)} h`}
        />
      </section>

      {/* --- Response trend (G2) --- */}
      <section className="mt-4">
        <ResponseTrend donorId={data.id} />
      </section>

      {/* --- Real-data ML predictions (Module Integration) --- */}
      <section className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <ChurnPredictionCard donorId={data.id} />
        <SurvivalCurve donorId={data.id} />
      </section>

      {/* --- Contact / profile row --- */}
      <section className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard icon={Phone} label="Phone" value={data.phone} />
        <StatCard
          icon={Languages}
          label="Preferred language"
          value={LANGUAGE_LABEL[data.preferred_language] ?? data.preferred_language}
        />
        <StatCard
          icon={Globe}
          label="Coordinates"
          value={`${data.lat.toFixed(3)}, ${data.lng.toFixed(3)}`}
        />
      </section>

      {/* --- Bridges --- */}
      <section className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Bridges</h2>
          <p className="text-xs text-white/40">
            {data.memberships.length} membership
            {data.memberships.length === 1 ? "" : "s"}
          </p>
        </div>

        {data.memberships.length === 0 ? (
          <div className="rounded-xl border border-white/10 bg-surface/20 p-8 text-center text-sm text-white/60">
            Not currently part of any bridge.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {data.memberships.map((m) => (
              <Link
                key={m.membership_id}
                href={`/bridges/${m.bridge_id}`}
                className="block rounded-xl border border-white/5 bg-surface/30 p-4 transition-colors hover:border-primary/40 hover:bg-surface/50"
                data-testid="donor-membership"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-medium text-white">{m.patient_name}</h3>
                    <p className="text-xs text-white/50">
                      {m.patient_age} · {m.bridge_name}
                    </p>
                  </div>
                  <span className="rounded bg-white/5 px-2 py-0.5 font-mono text-xs text-white/80">
                    {m.patient_blood_group}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-3 text-xs text-white/60">
                  <span>Joined {formatDate(m.joined_at)}</span>
                  <span>·</span>
                  <span className="capitalize">{m.role}</span>
                  <span>·</span>
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider",
                      m.status === "active"
                        ? "bg-emerald-500/15 text-emerald-300"
                        : "bg-white/5 text-white/40",
                    )}
                  >
                    {m.status}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>

    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Droplet;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-white/5 bg-surface/30 p-4">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="mt-1.5 truncate text-base font-semibold text-white" title={value}>
        {value}
      </div>
    </div>
  );
}
