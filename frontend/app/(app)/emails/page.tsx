"use client";

import { useQuery } from "@tanstack/react-query";
import { Mail, RefreshCw } from "lucide-react";
import { useState } from "react";

import { EmailChannelPanel } from "@/components/ui/email-channel-panel";
import { api, type EmailMessageOut } from "@/lib/api";
import { cn } from "@/lib/utils";

const TEMPLATE_LABELS: Record<string, string> = {
  caregiver_daily_digest: "Daily digest",
  caregiver_emergency_alert: "Emergency alert",
  coordinator_failure_alert: "Coordinator alert",
  ops_test: "Test send",
  recruit_success_caregiver__email_fallback: "Recruit success (email fallback)",
};

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "sent", label: "Sent" },
  { value: "mocked", label: "Mocked" },
  { value: "failed", label: "Failed" },
  { value: "skipped", label: "Skipped" },
];

export default function EmailsPage() {
  const [status, setStatus] = useState("");
  const [templateKey, setTemplateKey] = useState("");
  const [selected, setSelected] = useState<EmailMessageOut | null>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["emails-list", { status, templateKey }],
    queryFn: () =>
      api.listEmails({
        limit: 100,
        status: status || undefined,
        template_key: templateKey || undefined,
      }),
    refetchInterval: 15_000,
  });

  return (
    <div className="px-8 py-8" data-testid="emails-page">
      <header className="mb-6 flex items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Mail className="h-3.5 w-3.5" />
            Email channel
          </div>
          <h1 className="mt-1 text-3xl font-bold text-white">Outbound emails</h1>
          <p className="mt-1 text-sm text-white/60">
            SES sends — caregiver digests, emergency alerts, coordinator
            alerts, and WhatsApp fallbacks. Filter by status or template, click
            a row to preview the body.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-white/70 hover:border-white/20 hover:text-white"
          data-testid="emails-refresh"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </header>

      {/* KPI panel up top — same one used on /analytics */}
      <div className="mb-6">
        <EmailChannelPanel windowDays={30} />
      </div>

      {/* Filter bar */}
      <div
        className="mb-3 flex flex-wrap items-center gap-3 rounded-xl border border-white/5 bg-surface/40 p-3"
        data-testid="emails-filters"
      >
        <span className="text-[10px] uppercase tracking-wider text-white/40">
          Filter
        </span>
        <div className="flex gap-1">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setStatus(f.value)}
              className={cn(
                "rounded-full px-3 py-1 text-xs",
                status === f.value
                  ? "bg-primary/15 text-primary"
                  : "bg-white/5 text-white/60 hover:bg-white/10",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <input
          type="text"
          placeholder="template_key contains…"
          value={templateKey}
          onChange={(e) => setTemplateKey(e.target.value)}
          className="ml-auto w-64 rounded-md border border-white/10 bg-black/30 px-2 py-1 text-xs text-white placeholder:text-white/30"
          data-testid="emails-template-filter"
        />
      </div>

      {/* List + preview split */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_minmax(380px,2fr)]">
        <div
          className="overflow-hidden rounded-xl border border-white/5 bg-surface/40"
          data-testid="emails-list"
        >
          <div className="border-b border-white/5 px-3 py-2 text-[10px] uppercase tracking-wider text-white/40">
            {data ? `${data.total} message(s)` : "loading…"}
          </div>
          {isLoading ? (
            <div className="space-y-2 p-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="h-14 animate-pulse rounded-md border border-white/5 bg-surface/30"
                />
              ))}
            </div>
          ) : data && data.items.length === 0 ? (
            <p className="p-6 text-center text-xs text-white/40">
              No emails match the current filter.
            </p>
          ) : (
            <ul>
              {data?.items.map((e) => (
                <li key={e.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(e)}
                    data-testid="email-row"
                    className={cn(
                      "flex w-full flex-col gap-1 border-b border-white/5 px-3 py-2 text-left text-xs hover:bg-white/5",
                      selected?.id === e.id && "bg-primary/10",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-white/80">
                        {e.recipient_email}
                      </span>
                      <span
                        className={cn(
                          "shrink-0 rounded-full px-1.5 py-0.5 text-[10px] uppercase tracking-wider",
                          e.status === "sent"
                            ? "bg-emerald-500/15 text-emerald-300"
                            : e.status === "mocked"
                              ? "bg-amber-500/15 text-amber-300"
                              : e.status === "failed"
                                ? "bg-red-500/15 text-red-300"
                                : "bg-white/5 text-white/40",
                        )}
                      >
                        {e.status}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-2 text-[11px] text-white/40">
                      <span className="truncate">
                        {TEMPLATE_LABELS[e.template_key ?? ""] ?? e.template_key ?? "—"}
                      </span>
                      <span className="shrink-0 font-mono">
                        {new Date(e.created_at).toLocaleString()}
                      </span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Preview pane */}
        <aside
          className="rounded-xl border border-white/5 bg-surface/40 p-4"
          data-testid="email-preview"
        >
          {selected ? (
            <div>
              <header className="mb-3 border-b border-white/5 pb-2">
                <div className="text-[10px] uppercase tracking-wider text-white/40">
                  Subject
                </div>
                <h2 className="mt-0.5 text-base font-semibold text-white">
                  {selected.subject}
                </h2>
                <p className="mt-1 text-[11px] text-white/40">
                  {selected.from_email} → {selected.recipient_email}
                </p>
                <p className="text-[11px] text-white/40">
                  Template:{" "}
                  <span className="font-mono">{selected.template_key ?? "—"}</span>
                  {selected.is_mock ? (
                    <span className="ml-2 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">
                      MOCK
                    </span>
                  ) : null}
                </p>
                {selected.error_message ? (
                  <p className="mt-1 text-[11px] text-red-300">
                    Error: {selected.error_message}
                  </p>
                ) : null}
              </header>
              <pre
                className="whitespace-pre-wrap rounded-md bg-black/30 p-3 text-xs text-white/80"
                data-testid="email-body"
              >
                {selected.body}
              </pre>
            </div>
          ) : (
            <p className="py-12 text-center text-xs text-white/40">
              Select a message to preview its body.
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}
