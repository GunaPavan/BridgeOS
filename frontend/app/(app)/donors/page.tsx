"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { AlertTriangle, RefreshCw, Search, Users } from "lucide-react";

import { DonorCard } from "@/components/ui/donor-card";
import { api, type BloodGroup, type DonorFilters, type DonorSort } from "@/lib/api";
import { cn } from "@/lib/utils";

const BLOOD_GROUPS: BloodGroup[] = ["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"];

const SORTS: { value: DonorSort; label: string }[] = [
  { value: "name", label: "Name" },
  { value: "response_rate", label: "Response rate" },
  { value: "last_donation", label: "Last donation" },
  { value: "total_donations", label: "Total donations" },
  { value: "age", label: "Age" },
];

export default function DonorsPage() {
  const [search, setSearch] = useState("");
  const [bloodGroup, setBloodGroup] = useState<BloodGroup | null>(null);
  const [activeOnly, setActiveOnly] = useState(true);
  // Kell-negative filter removed: the Blood Warriors dataset doesn't carry
  // the kell-negative column, so the checkbox always returned an empty set.
  const [sort, setSort] = useState<DonorSort>("name");

  const filters: DonorFilters = {
    limit: 60,
    search: search || undefined,
    blood_group: bloodGroup ?? undefined,
    is_active: activeOnly ? true : undefined,
    sort,
    order: sort === "name" || sort === "age" ? "asc" : "desc",
  };

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["donors", filters],
    queryFn: () => api.listDonors(filters),
  });

  return (
    <div className="px-8 py-8">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Users className="h-3.5 w-3.5" />
            Donors
          </div>
          <h1 className="mt-1 text-3xl font-bold text-white">All Donors</h1>
          <p className="mt-1 text-sm text-white/60">
            {data
              ? `${data.total} donor${data.total === 1 ? "" : "s"} match the current filters.`
              : "Loading donors…"}
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

      {/* --- Filters bar --- */}
      <section className="mb-6 space-y-3 rounded-xl border border-white/5 bg-surface/30 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/40" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name…"
              aria-label="Search donors by name"
              className="w-full rounded-lg border border-white/10 bg-black/30 py-2 pl-9 pr-3 text-sm text-white placeholder:text-white/40 focus:border-accent/50 focus:outline-none"
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
              onChange={(e) => setSort(e.target.value as DonorSort)}
              className="rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white focus:border-accent/50 focus:outline-none"
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
          <FilterChip
            label="All groups"
            active={bloodGroup === null}
            onClick={() => setBloodGroup(null)}
          />
          {BLOOD_GROUPS.map((bg) => (
            <FilterChip
              key={bg}
              label={bg}
              active={bloodGroup === bg}
              onClick={() => setBloodGroup(bg)}
              mono
            />
          ))}
        </div>
      </section>

      {/* --- Body --- */}
      {isLoading ? <DonorsSkeleton /> : null}

      {error ? (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" />
            Could not load donors.
          </div>
          <p className="mt-1 text-red-300/80">
            Backend should be running at{" "}
            <code className="rounded bg-black/30 px-1">http://localhost:8000</code>. ({error.message})
          </p>
        </div>
      ) : null}

      {data && data.items.length === 0 ? (
        <div className="rounded-xl border border-white/10 bg-surface/20 p-12 text-center text-sm text-white/60">
          No donors match these filters. Try clearing some.
        </div>
      ) : null}

      {data && data.items.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {data.items.map((donor) => (
            <DonorCard key={donor.id} donor={donor} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function FilterChip({
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

function DonorsSkeleton() {
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
