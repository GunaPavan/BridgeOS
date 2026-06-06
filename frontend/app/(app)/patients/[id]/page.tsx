"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Building2,
  Calendar,
  Droplet,
  Globe,
  Languages,
  MapPin,
  Network,
  Repeat,
  ShieldCheck,
  Users,
} from "lucide-react";

import { CaregiverPanel } from "@/components/ui/caregiver-panel";
import { EmergencyButton } from "@/components/ui/emergency-button";
import { HealthBadge } from "@/components/ui/health-badge";
import { api } from "@/lib/api";
import { cn, displayOr, formatDate, formatDaysRelative, isMissing } from "@/lib/utils";

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

export default function PatientProfilePage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;

  const { data, isLoading, error } = useQuery({
    queryKey: ["patient", id],
    queryFn: () => api.getPatient(id as string),
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
          href="/patients"
          className="inline-flex items-center gap-2 text-sm text-white/70 hover:text-white"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to patients
        </Link>
        <p className="mt-6 text-red-300">
          Could not load this patient. {error?.message ?? "Unknown error."}
        </p>
      </div>
    );
  }

  return (
    <div className="px-8 py-8">
      <Link
        href="/patients"
        className="inline-flex items-center gap-2 text-sm text-white/60 hover:text-white"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to patients
      </Link>

      {/* --- Header --- */}
      <header className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-3xl font-bold text-white">{data.name}</h1>
            {data.kell_negative ? (
              <ShieldCheck
                className="h-5 w-5 text-accent"
                aria-label="Kell-negative — alloimmunization risk if mismatched"
              />
            ) : null}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-white/70">
            <span className="rounded-md bg-white/5 px-2 py-0.5 font-mono text-primary">
              {data.blood_group}
            </span>
            <span>{data.age} years old</span>
            {!isMissing(data.hospital) && (
              <>
                <span className="text-white/30">·</span>
                <Building2 className="h-3.5 w-3.5" /> {displayOr(data.hospital)}
              </>
            )}
            <span className="text-white/30">·</span>
            <MapPin className="h-3.5 w-3.5" /> {displayOr(data.city)}, {displayOr(data.state)}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {data.bridge_health ? <HealthBadge health={data.bridge_health} /> : null}
          <EmergencyButton patientId={data.id} patientName={data.name} />
        </div>
      </header>

      {/* --- Transfusion plan --- */}
      <section className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          icon={Repeat}
          label="Cadence"
          value={`every ${data.transfusion_cadence_days}d`}
        />
        <StatCard
          icon={Droplet}
          label="Last transfusion"
          value={formatDate(data.last_transfusion_date)}
        />
        <StatCard
          icon={Calendar}
          label="Next transfusion"
          value={formatDaysRelative(data.days_until_transfusion)}
        />
        <StatCard
          icon={Users}
          label="Donor cohort"
          value={data.has_bridge ? `${data.active_donor_count} active` : "no bridge"}
        />
      </section>

      {/* --- Profile + contact --- */}
      <section className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard
          icon={Languages}
          label="Preferred language"
          value={LANGUAGE_LABEL[data.preferred_language] ?? data.preferred_language}
        />
        <StatCard
          icon={ShieldCheck}
          label="Phenotype"
          value={
            data.extended_phenotype
              ? data.extended_phenotype
              : data.kell_negative
              ? "Kell-negative recipient"
              : "Standard ABO/Rh"
          }
        />
        <StatCard
          icon={Globe}
          label="Coordinates"
          value={`${data.lat.toFixed(3)}, ${data.lng.toFixed(3)}`}
        />
      </section>

      {/* --- G5: Caregiver communications panel --- */}
      <section className="mt-8">
        <CaregiverPanel
          patientId={data.id}
          caregiverName={data.caregiver_name}
          caregiverPhone={data.caregiver_phone}
          caregiverRelation={data.caregiver_relation}
        />
      </section>

      {/* --- Bridge link --- */}
      {data.bridge ? (
        <section className="mt-8">
          <h2 className="mb-3 text-lg font-semibold text-white">Blood Bridge</h2>
          <Link
            href={`/bridges/${data.bridge.bridge_id}`}
            className="block rounded-xl border border-white/10 bg-surface/30 p-5 transition-colors hover:border-primary/40 hover:bg-surface/50"
            data-testid="patient-bridge-link"
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Network className="h-4 w-4 text-primary" />
                  <h3 className="font-medium text-white">{data.bridge.bridge_name}</h3>
                </div>
                <p className="mt-1 text-sm text-white/60">
                  {data.bridge.active_donor_count} active / {data.bridge.total_donor_count} total
                  donors · created {formatDate(data.bridge.created_at)}
                </p>
              </div>
              <HealthBadge health={data.bridge.health} />
            </div>
          </Link>
        </section>
      ) : (
        <section className="mt-8 rounded-xl border border-amber-500/30 bg-amber-500/5 p-5 text-sm text-amber-200/90">
          This patient has no active Blood Bridge. Recruitment recommended.
        </section>
      )}

      {/* --- Projected transfusions --- */}
      <section className="mt-8">
        <h2 className="mb-3 text-lg font-semibold text-white">
          Projected next 6 transfusions
        </h2>
        {data.projected_transfusions.length === 0 ? (
          <p className="text-sm text-white/50">
            No transfusion history yet — schedule not predictable.
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {data.projected_transfusions.map((iso, idx) => (
              <div
                key={iso}
                className={cn(
                  "rounded-lg border border-white/10 bg-surface/30 p-3 text-sm",
                  idx === 0 && "border-primary/40 bg-primary/5",
                )}
              >
                <p className="text-xs text-white/40">#{idx + 1}</p>
                <p className="mt-1 font-medium text-white">{formatDate(iso)}</p>
              </div>
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
      <div
        className="mt-1.5 truncate text-base font-semibold text-white"
        title={value}
      >
        {value}
      </div>
    </div>
  );
}
