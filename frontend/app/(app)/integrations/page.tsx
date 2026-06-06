"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Brain,
  Cable,
  CheckCircle2,
  Database,
  Droplet,
  ExternalLink,
  Loader2,
  MessageSquare,
  RefreshCw,
  Server,
  ShieldCheck,
} from "lucide-react";

import { api, type IntegrationStatus } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";

const STATUS_STYLE: Record<
  IntegrationStatus["status"],
  { pill: string; dot: string; label: string }
> = {
  mocked: {
    pill: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    dot: "bg-amber-400",
    label: "MOCKED",
  },
  connected: {
    pill: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
    dot: "bg-emerald-400",
    label: "LIVE",
  },
  not_configured: {
    pill: "border-white/10 bg-white/5 text-white/40",
    dot: "bg-white/30",
    label: "NOT CONFIGURED",
  },
  error: {
    pill: "border-red-500/40 bg-red-500/10 text-red-300",
    dot: "bg-red-400",
    label: "ERROR",
  },
};

const ICONS: Record<string, typeof Cable> = {
  eraktkosh: Droplet,
  icmr_rdri: ShieldCheck,
  whatsapp_business: MessageSquare,
  aws_bedrock: Brain,
};

export default function IntegrationsPage() {
  const statusQuery = useQuery({
    queryKey: ["integrations"],
    queryFn: () => api.getIntegrations(),
  });

  const inventoryQuery = useQuery({
    queryKey: ["eraktkosh-inventory", "Hyderabad"],
    queryFn: () => api.getERaktKoshInventory({ city: "Hyderabad" }),
    staleTime: 60_000,
  });

  const icmrQuery = useQuery({
    queryKey: ["icmr-rdri-lookup", "B+"],
    queryFn: () =>
      api.lookupICMR({ bloodGroup: "B+", kellNegative: true }),
    staleTime: 60_000,
  });

  return (
    <div className="px-8 py-8">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Cable className="h-3.5 w-3.5" />
            Integrations
          </div>
          <h1 className="mt-1 text-3xl font-bold text-white">External systems</h1>
          <p className="mt-1 text-sm text-white/60">
            Bridge OS plugs into national infrastructure — augmenting what
            Blood Warriors already runs, not replacing it.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            statusQuery.refetch();
            inventoryQuery.refetch();
            icmrQuery.refetch();
          }}
          className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-white/70 hover:border-white/20 hover:text-white"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </header>

      {/* --- Status cards --- */}
      <section className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {statusQuery.isLoading
          ? Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="h-32 animate-pulse rounded-xl border border-white/5 bg-surface/30"
              />
            ))
          : statusQuery.data?.items.map((item) => (
              <IntegrationCard key={item.key} item={item} />
            ))}
      </section>

      {/* --- Live eRaktKosh sample --- */}
      <section className="mb-6 rounded-xl border border-white/5 bg-surface/40 p-5">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
              <Database className="h-3 w-3" />
              eRaktKosh sample — Hyderabad
            </div>
            <h2 className="mt-1 text-base font-semibold text-white">
              Live inventory pull
            </h2>
            {inventoryQuery.data ? (
              <p className="text-xs text-white/40">
                Fetched {new Date(inventoryQuery.data.fetched_at).toLocaleTimeString()}{" "}
                · {inventoryQuery.data.blood_banks.length} blood banks
              </p>
            ) : null}
          </div>
        </div>

        {inventoryQuery.isLoading ? (
          <Loader2 className="h-4 w-4 animate-spin text-white/40" />
        ) : inventoryQuery.error ? (
          <ErrorBanner message={inventoryQuery.error.message} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs" data-testid="inventory-table">
              <thead className="text-white/40">
                <tr>
                  <th className="py-2 pr-3 text-left font-medium">Blood bank</th>
                  {["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"].map((bg) => (
                    <th
                      key={bg}
                      className={cn(
                        "px-2 py-2 text-right font-mono font-medium",
                        bg.endsWith("-") && "text-accent/80",
                      )}
                    >
                      {bg}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {inventoryQuery.data?.blood_banks.map((b) => (
                  <tr key={b.name} className="border-t border-white/5">
                    <td className="py-2 pr-3">
                      <p className="font-medium text-white">{b.name}</p>
                      <p className="text-white/40">{b.phone}</p>
                    </td>
                    {["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"].map((bg) => {
                      const count = b.inventory[bg] ?? 0;
                      return (
                        <td
                          key={bg}
                          className={cn(
                            "px-2 py-2 text-right tabular-nums",
                            count === 0
                              ? "text-white/20"
                              : count < 3
                              ? "text-red-300"
                              : count < 8
                              ? "text-amber-300"
                              : "text-white",
                          )}
                        >
                          {count}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* --- Live ICMR RDRI sample --- */}
      <section className="rounded-xl border border-white/5 bg-surface/40 p-5">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
              <ShieldCheck className="h-3 w-3" />
              ICMR RDRI sample — B+ Kell-negative
            </div>
            <h2 className="mt-1 text-base font-semibold text-white">
              Rare phenotype registry lookup
            </h2>
            {icmrQuery.data ? (
              <p className="text-xs text-white/40">
                {icmrQuery.data.registered_donors.length} registered donors match
                this profile (Aarav's transfusion requirements)
              </p>
            ) : null}
          </div>
        </div>

        {icmrQuery.isLoading ? (
          <Loader2 className="h-4 w-4 animate-spin text-white/40" />
        ) : icmrQuery.error ? (
          <ErrorBanner message={icmrQuery.error.message} />
        ) : (
          <ul className="space-y-2" data-testid="icmr-donors-list">
            {icmrQuery.data?.registered_donors.map((d) => (
              <li
                key={d.registry_id}
                className="flex items-start justify-between rounded-lg border border-white/5 bg-black/20 p-3"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <p className="font-medium text-white">{d.name_initials}</p>
                    <span className="rounded bg-white/5 px-2 py-0.5 font-mono text-xs text-primary">
                      {d.blood_group}
                    </span>
                    {d.kell_negative ? (
                      <ShieldCheck className="h-3.5 w-3.5 text-accent" />
                    ) : null}
                  </div>
                  <p className="mt-1 text-xs text-white/60">{d.extended_phenotype}</p>
                  <p className="mt-1 text-xs text-white/40">
                    {d.city} · registered {d.registered_year}
                  </p>
                </div>
                <p className="font-mono text-[11px] text-white/30">
                  {d.registry_id}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function IntegrationCard({ item }: { item: IntegrationStatus }) {
  const style = STATUS_STYLE[item.status];
  const Icon = ICONS[item.key] ?? Server;
  return (
    <div
      className="rounded-xl border border-white/5 bg-surface/40 p-5"
      data-testid="integration-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-white/5 p-2">
            <Icon className="h-5 w-5 text-white/70" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-white">{item.name}</h3>
            <p className="mt-0.5 text-xs text-white/40">{item.phase}</p>
          </div>
        </div>
        <span
          className={cn(
            "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] uppercase tracking-wider",
            style.pill,
          )}
          data-testid="status-pill"
        >
          <span className={cn("h-1.5 w-1.5 rounded-full", style.dot)} />
          {style.label}
        </span>
      </div>

      <p className="mt-3 text-sm text-white/70">{item.description}</p>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-white/40">
        {item.sample_count !== null ? (
          <span className="flex items-center gap-1">
            <Database className="h-3 w-3" />
            {item.sample_count} records
          </span>
        ) : null}
        {item.last_sync ? (
          <span className="flex items-center gap-1">
            <CheckCircle2 className="h-3 w-3" />
            Last sync {formatDate(item.last_sync)}
          </span>
        ) : (
          <span>Awaiting configuration</span>
        )}
        {item.docs_url ? (
          <a
            href={item.docs_url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto inline-flex items-center gap-1 text-white/60 hover:text-white"
          >
            Docs <ExternalLink className="h-3 w-3" />
          </a>
        ) : null}
      </div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
      <div className="flex items-center gap-2 font-medium">
        <AlertTriangle className="h-3 w-3" />
        {message}
      </div>
    </div>
  );
}
