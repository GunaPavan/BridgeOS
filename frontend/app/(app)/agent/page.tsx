"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Globe,
  Loader2,
  MessageCircle,
  Sparkles,
  Send,
  X,
} from "lucide-react";

import {
  api,
  type AgentContextSource,
  type AgentLanguage,
  type AgentMessage,
  type AgentSessionSummary,
} from "@/lib/api";
import { AgentMessageBubble } from "@/components/ui/agent-message";
import { cn } from "@/lib/utils";

type ContextKind = "none" | "donor" | "bridge" | "patient";

const LANGUAGES: { code: AgentLanguage; label: string; native: string }[] = [
  { code: "en", label: "English", native: "English" },
  { code: "hi", label: "Hindi", native: "हिन्दी" },
  { code: "te", label: "Telugu", native: "తెలుగు" },
  { code: "ta", label: "Tamil", native: "தமிழ்" },
  { code: "mr", label: "Marathi", native: "मराठी" },
  { code: "bn", label: "Bengali", native: "বাংলা" },
  { code: "kn", label: "Kannada", native: "ಕನ್ನಡ" },
  { code: "gu", label: "Gujarati", native: "ગુજરાતી" },
];

const SAMPLE_QUERIES = [
  "Why is this donor at risk?",
  "Who should I recruit to replace them?",
  "When is the next transfusion?",
  "Draft a thank-you message",
];

export default function AgentPage() {
  const queryClient = useQueryClient();

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState<AgentLanguage>("en");
  const [sources, setSources] = useState<AgentContextSource[]>([]);
  const [sendError, setSendError] = useState<string | null>(null);

  // Context picker
  const [contextKind, setContextKind] = useState<ContextKind>("none");
  const [contextSearch, setContextSearch] = useState("");
  const [selectedContextId, setSelectedContextId] = useState<string | null>(null);
  const [selectedContextLabel, setSelectedContextLabel] = useState<string | null>(null);

  const threadEndRef = useRef<HTMLDivElement | null>(null);

  // Status + sessions list
  const statusQuery = useQuery({
    queryKey: ["agent", "status"],
    queryFn: () => api.getAgentStatus(),
  });
  const sessionsQuery = useQuery({
    queryKey: ["agent", "sessions"],
    queryFn: () => api.listAgentSessions(),
  });

  // Context search results (donors / bridges / patients)
  const donorSearchQuery = useQuery({
    queryKey: ["agent", "donors", contextSearch],
    queryFn: () => api.listDonors({ search: contextSearch, limit: 6 }),
    enabled: contextKind === "donor" && contextSearch.trim().length >= 2,
  });
  const bridgeListQuery = useQuery({
    queryKey: ["agent", "bridges"],
    queryFn: () => api.listBridges({ limit: 50 }),
    enabled: contextKind === "bridge",
  });
  const patientListQuery = useQuery({
    queryKey: ["agent", "patients", contextSearch],
    queryFn: () => api.listPatients({ search: contextSearch, limit: 8 }),
    enabled: contextKind === "patient" && contextSearch.trim().length >= 2,
  });

  const chatMutation = useMutation({
    mutationFn: () =>
      api.chatWithAgent({
        query: query.trim(),
        session_id: sessionId,
        donor_id: contextKind === "donor" ? selectedContextId : null,
        bridge_id: contextKind === "bridge" ? selectedContextId : null,
        patient_id: contextKind === "patient" ? selectedContextId : null,
        language,
      }),
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setMessages((prev) => [...prev, data.user_message, data.assistant_message]);
      setSources(data.sources);
      setQuery("");
      setSendError(null);
      queryClient.invalidateQueries({ queryKey: ["agent", "sessions"] });
    },
    onError: (err: Error) => setSendError(err.message || "Send failed"),
  });

  function handleSend() {
    if (!query.trim()) {
      setSendError("Type a question first");
      return;
    }
    chatMutation.mutate();
  }

  function startNewSession() {
    setSessionId(null);
    setMessages([]);
    setSources([]);
    setSendError(null);
  }

  async function openSession(sid: string) {
    const msgs = await api.getAgentSession(sid);
    setSessionId(sid);
    setMessages(msgs);
    setSources([]);
    setSendError(null);
  }

  function pickContext(kind: ContextKind, id: string | null, label: string | null) {
    setContextKind(kind);
    setSelectedContextId(id);
    setSelectedContextLabel(label);
    setContextSearch("");
  }

  // Auto-scroll to latest message
  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const contextActive = contextKind !== "none" && selectedContextId !== null;
  const isMock = !statusQuery.data?.is_live;

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col px-8 py-6">
      <header className="mb-4 flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Sparkles className="h-3.5 w-3.5" />
            Care Agent
          </div>
          <h1 className="mt-1 text-3xl font-bold text-white">
            Multilingual LLM assistant
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-white/60">
            Ask anything about a donor, bridge, or patient — the agent assembles
            the relevant facts and answers in any of {LANGUAGES.length} Indian languages.
          </p>
        </div>
        <ProviderPill
          provider={statusQuery.data?.provider ?? "mock"}
          model={statusQuery.data?.model ?? ""}
        />
      </header>

      {statusQuery.data?.multi_model ? (
        <MultiModelBanner status={statusQuery.data} />
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[280px_1fr_300px]">
        {/* Left: sessions */}
        <aside className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-white/5 bg-surface/40" data-testid="agent-sessions-panel">
          <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
            <span className="text-xs uppercase tracking-wider text-white/40">
              Sessions
            </span>
            <button
              type="button"
              onClick={startNewSession}
              data-testid="new-session-button"
              className="rounded-md border border-white/10 px-2 py-0.5 text-[11px] text-white/60 hover:text-white"
            >
              + New
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {sessionsQuery.isLoading ? (
              <Loader2 className="m-4 h-4 w-4 animate-spin text-white/40" />
            ) : sessionsQuery.data?.length === 0 ? (
              <div className="px-4 py-8 text-center text-xs text-white/40">
                No sessions yet — ask a question to start one.
              </div>
            ) : (
              <ul>
                {sessionsQuery.data?.map((s) => (
                  <SessionRow
                    key={s.session_id}
                    summary={s}
                    selected={s.session_id === sessionId}
                    onSelect={() => openSession(s.session_id)}
                  />
                ))}
              </ul>
            )}
          </div>
        </aside>

        {/* Middle: chat */}
        <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-white/5 bg-surface/40" data-testid="agent-chat-panel">
          {/* Context chips */}
          <div className="flex flex-wrap items-center gap-2 border-b border-white/5 px-4 py-3">
            <span className="text-[11px] uppercase tracking-wider text-white/40">
              Context:
            </span>
            <ContextChip
              active={contextKind === "none"}
              onClick={() => pickContext("none", null, null)}
              testid="context-chip-none"
            >
              None
            </ContextChip>
            <ContextChip
              active={contextKind === "donor"}
              onClick={() => pickContext("donor", null, null)}
              testid="context-chip-donor"
            >
              Donor
            </ContextChip>
            <ContextChip
              active={contextKind === "bridge"}
              onClick={() => pickContext("bridge", null, null)}
              testid="context-chip-bridge"
            >
              Bridge
            </ContextChip>
            <ContextChip
              active={contextKind === "patient"}
              onClick={() => pickContext("patient", null, null)}
              testid="context-chip-patient"
            >
              Patient
            </ContextChip>

            {contextActive ? (
              <span
                className="ml-2 inline-flex items-center gap-1 rounded-md border border-primary/30 bg-primary/10 px-2 py-0.5 text-[11px] text-primary"
                data-testid="selected-context-pill"
              >
                {selectedContextLabel}
                <button
                  type="button"
                  onClick={() => pickContext(contextKind, null, null)}
                  className="ml-0.5 rounded hover:bg-white/10"
                  aria-label="Clear context"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ) : null}

            {/* Language selector inline */}
            <div className="ml-auto flex items-center gap-2">
              <Globe className="h-3.5 w-3.5 text-white/40" />
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value as AgentLanguage)}
                data-testid="language-select"
                className="rounded-md border border-white/10 bg-black/30 px-2 py-1 text-xs text-white"
              >
                {LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label} ({l.native})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Context entity picker */}
          {contextKind !== "none" && !selectedContextId ? (
            <div className="border-b border-white/5 bg-black/20 px-4 py-3" data-testid="context-picker">
              <p className="mb-2 text-xs text-white/40">
                {contextKind === "bridge"
                  ? "Pick a bridge:"
                  : `Search for a ${contextKind}:`}
              </p>
              {contextKind !== "bridge" ? (
                <input
                  type="text"
                  placeholder="Type 2+ characters..."
                  value={contextSearch}
                  onChange={(e) => setContextSearch(e.target.value)}
                  className="w-full rounded-md border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white placeholder:text-white/30"
                  data-testid="context-search-input"
                  autoFocus
                />
              ) : null}

              <ContextPickerResults
                kind={contextKind}
                donorResults={donorSearchQuery.data?.items ?? []}
                bridgeResults={bridgeListQuery.data?.items ?? []}
                patientResults={patientListQuery.data?.items ?? []}
                onPick={pickContext}
              />
            </div>
          ) : null}

          {/* Thread */}
          <div
            className="flex-1 overflow-y-auto px-4 py-4"
            data-testid="agent-thread"
          >
            {messages.length === 0 ? (
              <EmptyChat
                onSampleClick={(s) => setQuery(s)}
                contextActive={contextActive}
              />
            ) : (
              <div className="space-y-4">
                {messages.map((m) => (
                  <AgentMessageBubble key={m.id} message={m} />
                ))}
                <div ref={threadEndRef} />
              </div>
            )}
          </div>

          {/* Composer */}
          <div className="border-t border-white/5 p-3">
            {sendError ? (
              <div className="mb-2 flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
                <AlertCircle className="h-3.5 w-3.5" />
                {sendError}
              </div>
            ) : null}
            <div className="flex items-end gap-2">
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                rows={2}
                placeholder="Ask the agent... (Shift+Enter for newline)"
                data-testid="agent-input"
                className="flex-1 resize-none rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-white/30"
              />
              <button
                type="button"
                onClick={handleSend}
                disabled={chatMutation.isPending}
                data-testid="agent-send-button"
                className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-white shadow-lg shadow-primary/20 transition hover:bg-primary/80 disabled:opacity-50"
              >
                {chatMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                Ask
              </button>
            </div>
          </div>
        </section>

        {/* Right: sources / context */}
        <aside className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-white/5 bg-surface/40" data-testid="agent-sources-panel">
          <div className="border-b border-white/5 px-4 py-3 text-xs uppercase tracking-wider text-white/40">
            Sources & memory
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {sources.length === 0 ? (
              <p className="text-xs text-white/40">
                {contextActive
                  ? "Ask a question — the agent will cite the live records it used."
                  : "Pick an entity from the Context chips above to give the agent memory."}
              </p>
            ) : (
              <ul className="space-y-2">
                {sources.map((s, i) => (
                  <li
                    key={`${s.kind}-${i}`}
                    className="rounded-md border border-white/10 bg-black/20 p-2"
                    data-testid="source-row"
                  >
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-white/40">
                        {s.kind}
                      </span>
                      <span className="text-xs font-medium text-white/80">
                        {s.label}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}

            {isMock ? (
              <div className="mt-4 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-[11px] text-amber-200/80">
                <div className="mb-1 flex items-center gap-1 font-medium">
                  <MessageCircle className="h-3 w-3" />
                  Mock LLM active
                </div>
                Set <code className="font-mono">BEDROCK_REGION</code> (AWS Bedrock
                multi-model — preferred) or <code className="font-mono">ANTHROPIC_API_KEY</code> for live LLM answers.
              </div>
            ) : null}
          </div>
        </aside>
      </div>
    </div>
  );
}

// ---------- Subcomponents ----------

function MultiModelBanner({
  status,
}: {
  status: {
    chat_model?: string | null;
    intent_model?: string | null;
    embedding_model?: string | null;
  };
}) {
  const shortId = (id?: string | null) => {
    if (!id) return "—";
    // Show the last meaningful chunk of the model id (e.g. "claude-3-5-sonnet-20241022-v2:0")
    return id.split(".").pop() ?? id;
  };
  return (
    <div
      data-testid="multi-model-indicator"
      className="mb-4 flex flex-col gap-1 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-200 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="font-semibold uppercase tracking-wider">
        Bedrock multi-model active
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-emerald-200/75">
        <span>
          Chat <span className="font-mono">{shortId(status.chat_model)}</span>
        </span>
        <span>·</span>
        <span>
          Intent{" "}
          <span className="font-mono">{shortId(status.intent_model)}</span>
        </span>
        <span>·</span>
        <span>
          Embed{" "}
          <span className="font-mono">{shortId(status.embedding_model)}</span>
        </span>
      </div>
    </div>
  );
}

function ProviderPill({ provider, model }: { provider: string; model: string }) {
  const isLive = provider !== "mock";
  return (
    <div
      data-testid="provider-pill"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] uppercase tracking-wider",
        isLive
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
          : "border-amber-500/40 bg-amber-500/10 text-amber-300",
      )}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          isLive ? "bg-emerald-400" : "bg-amber-400",
        )}
      />
      {provider}
      {model ? <span className="ml-1 font-mono normal-case opacity-60">{model}</span> : null}
    </div>
  );
}

function ContextChip({
  active,
  onClick,
  children,
  testid,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  testid?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      className={cn(
        "rounded-md border px-2 py-0.5 text-[11px] uppercase tracking-wider transition-colors",
        active
          ? "border-primary/40 bg-primary/15 text-primary"
          : "border-white/10 text-white/60 hover:border-white/20 hover:text-white",
      )}
    >
      {children}
    </button>
  );
}

function SessionRow({
  summary,
  selected,
  onSelect,
}: {
  summary: AgentSessionSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        data-testid="session-row"
        className={cn(
          "flex w-full flex-col items-start gap-1 border-b border-white/5 px-4 py-3 text-left transition-colors",
          selected ? "bg-primary/10" : "hover:bg-white/[0.03]",
        )}
      >
        <p className="line-clamp-2 text-sm text-white/80">
          {summary.last_user_query || "(no query)"}
        </p>
        <div className="flex items-center gap-2 text-[10px] text-white/30">
          <span>{summary.message_count} msgs</span>
          <span>·</span>
          <span>{summary.language}</span>
        </div>
      </button>
    </li>
  );
}

function ContextPickerResults({
  kind,
  donorResults,
  bridgeResults,
  patientResults,
  onPick,
}: {
  kind: ContextKind;
  donorResults: { id: string; name: string; blood_group: string }[];
  bridgeResults: { id: string; patient_name: string; blood_group: string }[];
  patientResults: { id: string; name: string; blood_group: string }[];
  onPick: (kind: ContextKind, id: string | null, label: string | null) => void;
}) {
  if (kind === "donor") {
    if (donorResults.length === 0) {
      return <p className="mt-2 text-[11px] text-white/40">No matches yet.</p>;
    }
    return (
      <ul className="mt-2 space-y-1">
        {donorResults.map((d) => (
          <li key={d.id}>
            <button
              type="button"
              onClick={() => onPick("donor", d.id, `Donor: ${d.name}`)}
              data-testid="context-pick-donor"
              className="flex w-full items-center justify-between rounded-md border border-white/5 px-2 py-1.5 text-left text-xs text-white/70 hover:border-white/15 hover:text-white"
            >
              <span>{d.name}</span>
              <span className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-primary">
                {d.blood_group}
              </span>
            </button>
          </li>
        ))}
      </ul>
    );
  }
  if (kind === "bridge") {
    return (
      <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto">
        {bridgeResults.map((b) => (
          <li key={b.id}>
            <button
              type="button"
              onClick={() =>
                onPick("bridge", b.id, `Bridge: ${b.patient_name}`)
              }
              data-testid="context-pick-bridge"
              className="flex w-full items-center justify-between rounded-md border border-white/5 px-2 py-1.5 text-left text-xs text-white/70 hover:border-white/15 hover:text-white"
            >
              <span>Bridge for {b.patient_name}</span>
              <span className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-primary">
                {b.blood_group}
              </span>
            </button>
          </li>
        ))}
      </ul>
    );
  }
  if (kind === "patient") {
    if (patientResults.length === 0) {
      return <p className="mt-2 text-[11px] text-white/40">No matches yet.</p>;
    }
    return (
      <ul className="mt-2 space-y-1">
        {patientResults.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => onPick("patient", p.id, `Patient: ${p.name}`)}
              data-testid="context-pick-patient"
              className="flex w-full items-center justify-between rounded-md border border-white/5 px-2 py-1.5 text-left text-xs text-white/70 hover:border-white/15 hover:text-white"
            >
              <span>{p.name}</span>
              <span className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-primary">
                {p.blood_group}
              </span>
            </button>
          </li>
        ))}
      </ul>
    );
  }
  return null;
}

function EmptyChat({
  onSampleClick,
  contextActive,
}: {
  onSampleClick: (s: string) => void;
  contextActive: boolean;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
      <Sparkles className="h-10 w-10 text-primary/40" />
      <div>
        <p className="text-base font-medium text-white/80">
          Ask the Care Agent a question
        </p>
        <p className="mt-1 text-xs text-white/40">
          {contextActive
            ? "Try one of these — the agent already has your selected entity in context."
            : "Pick a Donor / Bridge / Patient chip above for grounded answers."}
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {SAMPLE_QUERIES.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onSampleClick(s)}
            data-testid="sample-query"
            className="rounded-full border border-white/10 px-3 py-1 text-xs text-white/60 hover:border-white/20 hover:text-white"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
