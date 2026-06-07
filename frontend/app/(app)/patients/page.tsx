"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { AlertTriangle, RefreshCw, Search, UserCircle2 } from "lucide-react";

import { PatientCard } from "@/components/ui/patient-card";
import {
  api,
  type BloodGroup,
  type BridgeHealth,
  type PatientFilters,
  type PatientSort,
} from "@/lib/api";
import { cn } from "@/lib/utils";

// Full ABO + Rh set so patients can be filtered for any blood type the
// dataset carries (the donors page already supports this; patients was
// missing the four Rh-negative options).
const BLOOD_GROUPS: BloodGroup[] = [
  "O+", "A+", "B+", "AB+",
  "O-", "A-", "B-", "AB-",
];
const HEALTHS: { value: BridgeHealth; label: string }[] = [
  { value: "stable", label: "Stable" },
  { value: "at_risk", label: "At risk" },
  { value: "critical", label: "Critical" },
];

const SORTS: { value: PatientSort; label: string }[] = [
  { value: "name", label: "Name" },
  { value: "age", label: "Age" },
  { value: "last_transfusion", label: "Most urgent (oldest last transfusion)" },
];

export default function PatientsPage() {
  const [search, setSearch] = useState("");
  const [bloodGroup, setBloodGroup] = useState<BloodGroup | null>(null);
  const [healthFilter, setHealthFilter] = useState<BridgeHealth | null>(null);
  const [activeOnly, setActiveOnly] = useState(true);
  const [sort, setSort] = useState<PatientSort>("name");

  const filters: PatientFilters = {
    limit: 60,
    search: search || undefined,
    blood_group: bloodGroup ?? undefined,
    active: activeOnly ? true : undefined,
    bridge_health: healthFilter ?? undefined,
    sort,
    order: sort === "last_transfusion" ? "asc" : "asc",
  };

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["patients", filters],
    queryFn: () => api.listPatients(filters),
  });

  return (
    <div className="px-8 py-8">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <UserCircle2 className="h-3.5 w-3.5" />
            Patients
          </div>
          <h1 className="mt-1 text-3xl font-bold text-white">All Patients</h1>
          <p className="mt-1 text-sm text-white/60">
            {data
              ? `${data.total} patient${data.total === 1 ? "" : "s"} on the recurring care roster.`
              : "Loading patients…"}
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

      <section className="mb-6 space-y-3 rounded-xl border border-white/5 bg-surface/30 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/40" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name…"
              aria-label="Search patients by name"
              className="w-full rounded-lg border border-white/10 bg-black/30 py-2 pl-9 pr-3 text-sm text-white placeholder:text-white/40 focus:border-primary/50 focus:outline-none"
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-white/70">
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={(e) => setActiveOnly(e.target.checked)}
              className="h-3.5 w-3.5 accent-primary"
            />
            Active only
          </label>

          <div className="ml-auto flex items-center gap-2 text-sm text-white/70">
            <label htmlFor="sort">Sort by</label>
            <select
              id="sort"
              value={sort}
              onChange={(e) => setSort(e.target.value as PatientSort)}
              className="rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white focus:border-primary/50 focus:outline-none"
            >
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 pt-1" aria-label="Blood group filter">
          <Chip label="All groups" active={bloodGroup === null} onClick={() => setBloodGroup(null)} />
          {BLOOD_GROUPS.map((bg) => (
            <Chip
              key={bg}
              label={bg}
              active={bloodGroup === bg}
              onClick={() => setBloodGroup(bg)}
              mono
            />
          ))}
        </div>

        <div className="flex flex-wrap gap-2" aria-label="Bridge health filter">
          <Chip
            label="Any health"
            active={healthFilter === null}
            onClick={() => setHealthFilter(null)}
          />
          {HEALTHS.map((h) => (
            <Chip
              key={h.value}
              label={h.label}
              active={healthFilter === h.value}
              onClick={() => setHealthFilter(h.value)}
            />
          ))}
        </div>
      </section>

      {isLoading ? <PatientsSkeleton /> : null}

      {error ? (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" />
            Could not load patients.
          </div>
          <p className="mt-1 text-red-300/80">
            Could not reach the Bridge OS API. ({error.message})
          </p>
        </div>
      ) : null}

      {data && data.items.length === 0 ? (
        <div className="rounded-xl border border-white/10 bg-surface/20 p-12 text-center text-sm text-white/60">
          No patients match these filters. Try clearing some.
        </div>
      ) : null}

      {data && data.items.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {data.items.map((p) => (
            <PatientCard key={p.id} patient={p} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Chip({
  label,
  active,
  onClick,
  mono = false,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  mono?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1 text-xs transition-colors",
        mono && "font-mono",
        active
          ? "border-primary/50 bg-primary/15 text-primary"
          : "border-white/10 bg-transparent text-white/60 hover:border-white/20 hover:text-white",
      )}
      aria-pressed={active}
    >
      {label}
    </button>
  );
}

function PatientsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          className="h-44 animate-pulse rounded-xl border border-white/5 bg-surface/30"
        />
      ))}
    </div>
  );
}
