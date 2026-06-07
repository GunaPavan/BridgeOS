"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Bell,
  BrainCircuit,
  Cable,
  CheckCircle2,
  Cog,
  Database,
  KeyRound,
  Languages,
  MessageSquare,
  Palette,
  Server,
  Sparkles,
  Wand2,
} from "lucide-react";

import { api } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

export default function SettingsPage() {
  const { show } = useToast();

  const integrationsQuery = useQuery({
    queryKey: ["integrations"],
    queryFn: () => api.getIntegrations(),
  });
  const agentQuery = useQuery({
    queryKey: ["agent", "status"],
    queryFn: () => api.getAgentStatus(),
  });
  const whatsappQuery = useQuery({
    queryKey: ["whatsapp", "status"],
    queryFn: () => api.getWhatsAppStatus(),
  });

  return (
    <div className="px-8 py-8" data-testid="settings-page">
      <header className="mb-6">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
          <Cog className="h-3.5 w-3.5" />
          Settings
        </div>
        <h1 className="mt-1 text-3xl font-bold text-white">System configuration</h1>
        <p className="mt-1 max-w-2xl text-sm text-white/60">
          Inspect what's wired into this Bridge OS deployment. Connection state,
          enabled features, and the active LLM/WhatsApp providers.
        </p>
      </header>

      <section className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ProviderCard
          icon={Sparkles}
          title="Care Agent"
          loading={agentQuery.isLoading}
          provider={agentQuery.data?.provider ?? "mock"}
          model={agentQuery.data?.model ?? ""}
          isLive={agentQuery.data?.is_live ?? false}
          envHint="BEDROCK_REGION (preferred) or ANTHROPIC_API_KEY"
        />
        <ProviderCard
          icon={MessageSquare}
          title="WhatsApp (Twilio)"
          loading={whatsappQuery.isLoading}
          provider={whatsappQuery.data?.is_live ? "twilio" : "mock"}
          model={whatsappQuery.data?.from_number ?? ""}
          isLive={whatsappQuery.data?.is_live ?? false}
          envHint="TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN"
        />
        <ProviderCard
          icon={Database}
          title="Data layer"
          loading={false}
          provider="sqlite"
          model="local development"
          isLive={true}
          envHint="POSTGRES_URL to switch to Docker Postgres + pgvector"
        />
      </section>

      {/* Integration mirror */}
      <section className="mb-6 rounded-xl border border-white/5 bg-surface/40 p-5">
        <div className="mb-4 flex items-center gap-2">
          <Cable className="h-4 w-4 text-accent" />
          <h2 className="text-sm font-semibold text-white">External integrations</h2>
        </div>
        {integrationsQuery.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : (
          <ul className="space-y-2" data-testid="integrations-list">
            {integrationsQuery.data?.items.map((item) => (
              <li
                key={item.key}
                className="flex items-center justify-between rounded-lg border border-white/5 bg-black/20 p-3"
                data-testid="integration-status-row"
              >
                <div>
                  <p className="text-sm font-medium text-white">{item.name}</p>
                  <p className="text-xs text-white/40">{item.phase} · {item.description}</p>
                </div>
                <StatusPill status={item.status} />
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Feature toggles */}
      <section className="mb-6 rounded-xl border border-white/5 bg-surface/40 p-5">
        <div className="mb-4 flex items-center gap-2">
          <Wand2 className="h-4 w-4 text-accent" />
          <h2 className="text-sm font-semibold text-white">Features</h2>
        </div>
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <FeatureToggle
            icon={BrainCircuit}
            title="Cohort Stability Predictor"
            description="XGBoost + SHAP explanations on every bridge."
            enabled
            onPing={() =>
              show({
                title: "Predictor is live",
                description: "Toggle is read-only in this build — model loads at API startup.",
                variant: "info",
              })
            }
          />
          <FeatureToggle
            icon={Sparkles}
            title="Multilingual Care Agent"
            description="8 Indian languages with cohort-aware context."
            enabled
            onPing={() =>
              show({
                title: "Care Agent ready",
                description:
                  agentQuery.data?.is_live
                    ? `Using ${agentQuery.data.provider} (${agentQuery.data.model}).`
                    : "Running in mock mode — set ANTHROPIC_API_KEY for live LLM.",
                variant: agentQuery.data?.is_live ? "success" : "info",
              })
            }
          />
          <FeatureToggle
            icon={MessageSquare}
            title="WhatsApp via Twilio"
            description="Real outbound messages + inbound webhook."
            enabled
            onPing={() =>
              show({
                title: "Sent a test ping",
                description: whatsappQuery.data?.is_live
                  ? "Live Twilio — would have sent a real WhatsApp."
                  : "Mock mode — no real send happened.",
                variant: whatsappQuery.data?.is_live ? "success" : "info",
              })
            }
          />
          <FeatureToggle
            icon={Languages}
            title="Multilingual templates"
            description="Slot reminders + thank-yous in the donor's language."
            enabled
          />
          <FeatureToggle
            icon={KeyRound}
            title="Cognito RBAC sign-in"
            description="4 roles (admin · coordinator · donor · patient). PostConfirmation Lambda auto-assigns self-signups."
            enabled
          />
          <FeatureToggle
            icon={Palette}
            title="Dark theme"
            description="Coral + teal on navy. Only theme available in this build."
            enabled
          />
        </ul>
      </section>

      {/* Build info */}
      <section className="rounded-xl border border-white/5 bg-surface/40 p-5">
        <div className="mb-4 flex items-center gap-2">
          <Server className="h-4 w-4 text-accent" />
          <h2 className="text-sm font-semibold text-white">About this build</h2>
        </div>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <BuildStat label="Backend tests" value="170" />
          <BuildStat label="Frontend tests" value="89+" />
          <BuildStat label="Live E2E" value="54+" />
          <BuildStat label="API endpoints" value="34" />
        </div>
        <p className="mt-4 text-xs text-white/40">
          Built by AlgoWarriors for the AI for Good Hackathon 2026 — Blend360,
          with Blood Warriors Foundation and HackCulture as impact partners.
        </p>
      </section>
    </div>
  );
}

// ---------- Subcomponents ----------

function ProviderCard({
  icon: Icon,
  title,
  loading,
  provider,
  model,
  isLive,
  envHint,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  loading: boolean;
  provider: string;
  model: string;
  isLive: boolean;
  envHint: string;
}) {
  return (
    <div
      data-testid="provider-card"
      className="rounded-xl border border-white/5 bg-surface/40 p-5"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-primary/10 p-2 ring-1 ring-primary/20">
            <Icon className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">{title}</h3>
            <p className="mt-0.5 text-[11px] uppercase tracking-wider text-white/40">
              {loading ? "—" : provider}
            </p>
          </div>
        </div>
        {loading ? (
          <Skeleton className="h-5 w-12 rounded-full" />
        ) : (
          <span
            data-testid="provider-mode-pill"
            className={cn(
              "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
              isLive
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                : "border-amber-500/40 bg-amber-500/10 text-amber-300",
            )}
          >
            {isLive ? "Live" : "Mock"}
          </span>
        )}
      </div>
      {loading ? (
        <Skeleton className="mt-3 h-3 w-3/4" />
      ) : (
        <p className="mt-3 font-mono text-xs text-white/60">{model || "—"}</p>
      )}
      <p className="mt-2 text-[11px] text-white/40">
        Set <code className="font-mono text-white/60">{envHint}</code>
      </p>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    mocked: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    connected: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
    not_configured: "border-white/10 bg-white/5 text-white/40",
    error: "border-red-500/40 bg-red-500/10 text-red-300",
  };
  const cls = map[status] ?? map.not_configured;
  return (
    <span
      data-testid="integration-pill"
      className={cn(
        "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
        cls,
      )}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

function FeatureToggle({
  icon: Icon,
  title,
  description,
  enabled,
  onPing,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  enabled: boolean;
  onPing?: () => void;
}) {
  return (
    <li className="rounded-lg border border-white/5 bg-black/20 p-3" data-testid="feature-toggle">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Icon className="mt-0.5 h-4 w-4 text-accent" />
          <div>
            <p className="text-sm font-medium text-white">{title}</p>
            <p className="mt-0.5 text-xs text-white/55">{description}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {onPing ? (
            <button
              type="button"
              onClick={onPing}
              data-testid="feature-ping"
              className="rounded border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-white/60 hover:border-white/30 hover:text-white"
            >
              <Bell className="inline h-2.5 w-2.5" /> ping
            </button>
          ) : null}
          <span
            data-testid="feature-state"
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
              enabled
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                : "border-white/10 bg-white/5 text-white/40",
            )}
          >
            <CheckCircle2 className="h-2.5 w-2.5" />
            {enabled ? "On" : "Off"}
          </span>
        </div>
      </div>
    </li>
  );
}

function BuildStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/5 bg-black/20 p-3">
      <p className="bg-gradient-to-r from-primary to-accent bg-clip-text text-xl font-bold text-transparent">
        {value}
      </p>
      <p className="mt-1 text-[10px] uppercase tracking-wider text-white/40">
        {label}
      </p>
    </div>
  );
}
