"use client";

import { useMemo, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Info,
  Loader2,
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  Send,
  Sparkles,
} from "lucide-react";

import {
  api,
  type MessageTemplate,
  type SendMessageRequest,
  type WhatsAppMessage,
} from "@/lib/api";
import { ConversationRow } from "@/components/ui/conversation-row";
import { MessageBubble } from "@/components/ui/message-bubble";
import { cn } from "@/lib/utils";

export default function WhatsAppPage() {
  const queryClient = useQueryClient();

  const [selectedDonorId, setSelectedDonorId] = useState<string | null>(null);
  const [selectedBridgeId, setSelectedBridgeId] = useState<string | null>(null);
  const [composeMode, setComposeMode] = useState<"template" | "free">("template");
  const [selectedTemplate, setSelectedTemplate] = useState<string>("slot_reminder");
  const [freeText, setFreeText] = useState<string>("");
  const [sendError, setSendError] = useState<string | null>(null);
  const [showNewSearch, setShowNewSearch] = useState<boolean>(false);
  const [newSearchTerm, setNewSearchTerm] = useState<string>("");
  // G4: language override for the template send. Null = use donor's preferred_language.
  const [languageOverride, setLanguageOverride] = useState<string | null>(null);

  const statusQuery = useQuery({
    queryKey: ["whatsapp", "status"],
    queryFn: () => api.getWhatsAppStatus(),
  });

  const templatesQuery = useQuery({
    queryKey: ["whatsapp", "templates"],
    queryFn: () => api.listWhatsAppTemplates(),
    staleTime: Infinity,
  });

  const conversationsQuery = useQuery({
    queryKey: ["whatsapp", "conversations"],
    queryFn: () => api.listWhatsAppConversations(),
    refetchInterval: 5000,
  });

  // Selected donor's full thread + bridges
  const threadQuery = useQuery({
    queryKey: ["whatsapp", "thread", selectedDonorId],
    queryFn: () => api.getWhatsAppThread(selectedDonorId!),
    enabled: !!selectedDonorId,
    refetchInterval: 3000,
  });

  const donorDetailQuery = useQuery({
    queryKey: ["donor", selectedDonorId],
    queryFn: () => api.getDonor(selectedDonorId!),
    enabled: !!selectedDonorId,
  });

  const newDonorSearchQuery = useQuery({
    queryKey: ["donors", "search", newSearchTerm],
    queryFn: () => api.listDonors({ search: newSearchTerm, limit: 8 }),
    enabled: showNewSearch && newSearchTerm.trim().length >= 2,
  });

  // Auto-populate bridge selection from donor's memberships
  const donorBridges = donorDetailQuery.data?.memberships ?? [];
  const activeBridge = useMemo(
    () => donorBridges.find((m) => m.status === "active") ?? donorBridges[0] ?? null,
    [donorBridges],
  );
  const effectiveBridgeId = selectedBridgeId ?? activeBridge?.bridge_id ?? null;

  const sendMutation = useMutation({
    mutationFn: (payload: SendMessageRequest) => api.sendWhatsApp(payload),
    onSuccess: () => {
      setFreeText("");
      setSendError(null);
      queryClient.invalidateQueries({ queryKey: ["whatsapp", "conversations"] });
      queryClient.invalidateQueries({
        queryKey: ["whatsapp", "thread", selectedDonorId],
      });
    },
    onError: (err: Error) => setSendError(err.message || "Send failed"),
  });

  function handleSend() {
    if (!selectedDonorId) return;
    if (composeMode === "free") {
      if (!freeText.trim()) {
        setSendError("Message body is required");
        return;
      }
      sendMutation.mutate({ donor_id: selectedDonorId, body: freeText.trim() });
    } else {
      const template = templatesQuery.data?.find((t) => t.key === selectedTemplate);
      sendMutation.mutate({
        donor_id: selectedDonorId,
        template_key: selectedTemplate,
        bridge_id: template?.requires_bridge ? effectiveBridgeId : null,
        language: (languageOverride as
          | "en"
          | "hi"
          | "te"
          | "ta"
          | "mr"
          | "bn"
          | "kn"
          | "gu"
          | null) ?? undefined,
      });
    }
  }

  const isLive = statusQuery.data?.is_live ?? false;

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col px-8 py-6">
      <header className="mb-4 flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <MessageSquare className="h-3.5 w-3.5" />
            WhatsApp
          </div>
          <h1 className="mt-1 text-3xl font-bold text-white">Donor messaging</h1>
          <p className="mt-1 max-w-2xl text-sm text-white/60">
            Send slot reminders, recruitment invites, and thank-yous over the same
            channel donors already use. {isLive ? "Live via Twilio." : "Mock mode — messages persist locally; configure TWILIO_* env vars to go live."}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <TwilioStatusPill isLive={isLive} loading={statusQuery.isLoading} />
          <button
            type="button"
            onClick={() => {
              conversationsQuery.refetch();
              if (selectedDonorId) threadQuery.refetch();
            }}
            className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-white/70 hover:border-white/20 hover:text-white"
            data-testid="refresh-button"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
        </div>
      </header>

      {/* 3-column layout */}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[300px_1fr_320px]">
        {/* --- Left: conversation list --- */}
        <aside
          className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-white/5 bg-surface/40"
          data-testid="conversation-list"
        >
          <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
            <span className="text-xs uppercase tracking-wider text-white/40">
              Conversations ({conversationsQuery.data?.total ?? 0})
            </span>
            <button
              type="button"
              onClick={() => setShowNewSearch((v) => !v)}
              className="inline-flex items-center gap-1 rounded-md border border-white/10 px-2 py-0.5 text-[11px] text-white/60 hover:border-white/20 hover:text-white"
              data-testid="new-conversation-button"
            >
              <Plus className="h-3 w-3" />
              New
            </button>
          </div>

          {showNewSearch ? (
            <div className="border-b border-white/5 p-3" data-testid="new-conversation-panel">
              <div className="flex items-center gap-2 rounded-md border border-white/10 bg-black/30 px-2">
                <Search className="h-3.5 w-3.5 text-white/40" />
                <input
                  type="text"
                  autoFocus
                  placeholder="Search donor by name..."
                  value={newSearchTerm}
                  onChange={(e) => setNewSearchTerm(e.target.value)}
                  className="w-full bg-transparent py-1.5 text-sm text-white placeholder:text-white/30 focus:outline-none"
                  data-testid="new-conversation-search"
                />
              </div>
              {newSearchTerm.trim().length >= 2 ? (
                newDonorSearchQuery.isLoading ? (
                  <p className="mt-2 text-xs text-white/40">Searching...</p>
                ) : newDonorSearchQuery.data &&
                  newDonorSearchQuery.data.items.length > 0 ? (
                  <ul className="mt-2 space-y-1">
                    {newDonorSearchQuery.data.items.map((d) => (
                      <li key={d.id}>
                        <button
                          type="button"
                          data-testid="new-conversation-donor"
                          onClick={() => {
                            setSelectedDonorId(d.id);
                            setSelectedBridgeId(null);
                            setShowNewSearch(false);
                            setNewSearchTerm("");
                          }}
                          className="flex w-full items-center justify-between gap-2 rounded-md border border-white/5 px-2 py-1.5 text-left text-xs text-white/70 hover:border-white/15 hover:text-white"
                        >
                          <span className="truncate">{d.name}</span>
                          <span className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-primary">
                            {d.blood_group}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-xs text-white/40">No matches.</p>
                )
              ) : (
                <p className="mt-2 text-[11px] text-white/40">
                  Type 2+ characters to search.
                </p>
              )}
            </div>
          ) : null}

          <div className="flex-1 overflow-y-auto">
            {conversationsQuery.isLoading ? (
              <LoadingRow />
            ) : conversationsQuery.data?.conversations.length === 0 ? (
              <EmptyConversations />
            ) : (
              <ul>
                {conversationsQuery.data?.conversations.map((c) => {
                  // G5: caregiver rows route to the patient profile so the
                  // CaregiverPanel handles the thread + ad-hoc send.
                  if (c.kind === "caregiver" && c.caregiver) {
                    const patientId = c.caregiver.patient_id;
                    return (
                      <ConversationRow
                        key={`caregiver:${patientId}`}
                        conversation={c}
                        selected={false}
                        onSelect={() => {
                          window.location.href = `/patients/${patientId}`;
                        }}
                      />
                    );
                  }
                  if (!c.donor) return null;
                  const donorId = c.donor.id;
                  return (
                    <ConversationRow
                      key={`donor:${donorId}`}
                      conversation={c}
                      selected={donorId === selectedDonorId}
                      onSelect={() => {
                        setSelectedDonorId(donorId);
                        setSelectedBridgeId(null);
                      }}
                    />
                  );
                })}
              </ul>
            )}
          </div>
        </aside>

        {/* --- Middle: thread --- */}
        <section
          className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-white/5 bg-surface/40"
          data-testid="thread-panel"
        >
          {!selectedDonorId ? (
            <EmptyThread
              hasConversations={(conversationsQuery.data?.total ?? 0) > 0}
            />
          ) : threadQuery.isLoading ? (
            <LoadingRow />
          ) : threadQuery.data ? (
            <>
              <ThreadHeader thread={threadQuery.data} />
              <ThreadBody messages={threadQuery.data.messages} />
            </>
          ) : null}
        </section>

        {/* --- Right: compose --- */}
        <aside
          className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-white/5 bg-surface/40"
          data-testid="compose-panel"
        >
          <div className="border-b border-white/5 px-4 py-3 text-xs uppercase tracking-wider text-white/40">
            Compose
          </div>

          {!selectedDonorId ? (
            <div className="flex flex-1 items-center justify-center px-4 text-center text-xs text-white/40">
              Select a donor to send a message.
            </div>
          ) : (
            <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
              {/* Mode toggle */}
              <div
                className="grid grid-cols-2 gap-1 rounded-lg border border-white/10 p-1"
                role="tablist"
              >
                <button
                  type="button"
                  role="tab"
                  data-testid="mode-template"
                  aria-selected={composeMode === "template"}
                  onClick={() => setComposeMode("template")}
                  className={cn(
                    "rounded-md px-2 py-1 text-xs font-medium transition-colors",
                    composeMode === "template"
                      ? "bg-primary/20 text-primary"
                      : "text-white/60 hover:text-white",
                  )}
                >
                  Template
                </button>
                <button
                  type="button"
                  role="tab"
                  data-testid="mode-free"
                  aria-selected={composeMode === "free"}
                  onClick={() => setComposeMode("free")}
                  className={cn(
                    "rounded-md px-2 py-1 text-xs font-medium transition-colors",
                    composeMode === "free"
                      ? "bg-primary/20 text-primary"
                      : "text-white/60 hover:text-white",
                  )}
                >
                  Free text
                </button>
              </div>

              {composeMode === "template" ? (
                <>
                  <label className="text-xs text-white/40">Template</label>
                  <select
                    data-testid="template-select"
                    value={selectedTemplate}
                    onChange={(e) => setSelectedTemplate(e.target.value)}
                    className="rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                  >
                    {templatesQuery.data?.map((t) => (
                      <option key={t.key} value={t.key}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                  {donorBridges.length > 0 ? (
                    <>
                      <label className="text-xs text-white/40">
                        Bridge context
                      </label>
                      <select
                        data-testid="bridge-select"
                        value={effectiveBridgeId ?? ""}
                        onChange={(e) => setSelectedBridgeId(e.target.value || null)}
                        className="rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                      >
                        {donorBridges.map((m) => (
                          <option key={m.bridge_id} value={m.bridge_id}>
                            {m.patient_name} ({m.bridge_status})
                          </option>
                        ))}
                      </select>
                    </>
                  ) : null}
                  <label className="text-xs text-white/40">Language</label>
                  <select
                    data-testid="template-language-select"
                    value={
                      languageOverride ??
                      donorDetailQuery.data?.preferred_language ??
                      "en"
                    }
                    onChange={(e) => setLanguageOverride(e.target.value)}
                    className="rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white"
                  >
                    <option value="en">English</option>
                    <option value="hi">हिन्दी (Hindi)</option>
                    <option value="te">తెలుగు (Telugu)</option>
                    <option value="ta">தமிழ் (Tamil)</option>
                    <option value="mr">मराठी (Marathi)</option>
                    <option value="bn">বাংলা (Bengali)</option>
                    <option value="kn">ಕನ್ನಡ (Kannada)</option>
                    <option value="gu">ગુજરાતી (Gujarati)</option>
                  </select>
                  {languageOverride &&
                  donorDetailQuery.data?.preferred_language &&
                  languageOverride !== donorDetailQuery.data.preferred_language ? (
                    <p className="text-[10px] text-amber-300/80">
                      Overriding{" "}
                      {donorDetailQuery.data.name.split(" ")[0]}'s preferred
                      language ({donorDetailQuery.data.preferred_language}).
                    </p>
                  ) : null}
                  <TemplatePreview
                    templates={templatesQuery.data ?? []}
                    selectedKey={selectedTemplate}
                    language={
                      languageOverride ??
                      donorDetailQuery.data?.preferred_language ??
                      "en"
                    }
                  />
                </>
              ) : (
                <textarea
                  data-testid="free-textarea"
                  value={freeText}
                  onChange={(e) => setFreeText(e.target.value)}
                  rows={6}
                  placeholder="Type a message..."
                  className="resize-none rounded-md border border-white/10 bg-black/30 p-3 text-sm text-white placeholder:text-white/30"
                />
              )}

              {sendError ? (
                <div className="flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
                  <AlertCircle className="h-3.5 w-3.5" />
                  {sendError}
                </div>
              ) : null}

              <button
                type="button"
                onClick={handleSend}
                disabled={sendMutation.isPending}
                className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-white shadow-lg shadow-primary/20 transition hover:bg-primary/80 disabled:opacity-50"
                data-testid="send-button"
              >
                {sendMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                Send WhatsApp
              </button>

              {/* Sandbox info */}
              {!isLive && statusQuery.data ? (
                <div className="mt-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-[11px] text-amber-200/80">
                  <div className="mb-1 flex items-center gap-1 font-medium">
                    <Info className="h-3 w-3" />
                    Mock mode active
                  </div>
                  Set <code className="font-mono">TWILIO_ACCOUNT_SID</code> +{" "}
                  <code className="font-mono">TWILIO_AUTH_TOKEN</code> to send real messages.
                </div>
              ) : null}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

// ---------- subcomponents ----------

function TwilioStatusPill({
  isLive,
  loading,
}: {
  isLive: boolean;
  loading: boolean;
}) {
  if (loading) return null;
  return (
    <span
      data-testid="twilio-status-pill"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] uppercase tracking-wider",
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
      {isLive ? "Twilio live" : "Mock mode"}
    </span>
  );
}

function ThreadHeader({
  thread,
}: {
  thread: { donor: { id: string; name: string; blood_group: string; city: string; phone: string } };
}) {
  return (
    <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
      <div>
        <h2 className="text-base font-semibold text-white" data-testid="thread-donor-name">
          {thread.donor.name}
        </h2>
        <p className="text-xs text-white/40">
          {thread.donor.blood_group} · {thread.donor.city} · {thread.donor.phone}
        </p>
      </div>
    </div>
  );
}

function ThreadBody({ messages }: { messages: WhatsAppMessage[] }) {
  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-xs text-white/40">
        No messages yet — send the first one.
      </div>
    );
  }
  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4" data-testid="thread-messages">
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
    </div>
  );
}

function TemplatePreview({
  templates,
  selectedKey,
  language,
}: {
  templates: MessageTemplate[];
  selectedKey: string;
  language: string;
}) {
  const template = templates.find((t) => t.key === selectedKey);
  if (!template) return null;
  const lang =
    template.bodies[language] !== undefined && template.bodies[language] !== ""
      ? language
      : "en";
  const body = template.bodies[lang] ?? "";
  return (
    <div
      data-testid="template-preview"
      data-language={lang}
      className="rounded-md border border-white/10 bg-black/30 p-3 text-xs text-white/70"
    >
      <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-white/40">
        <span className="inline-flex items-center gap-1">
          <Sparkles className="h-3 w-3" />
          Preview
        </span>
        <span className="rounded bg-accent/15 px-1.5 py-0.5 font-mono text-accent">
          {lang}
          {lang !== language ? " (fallback)" : ""}
        </span>
      </div>
      <p className="whitespace-pre-wrap" data-testid="template-preview-body">
        {body}
      </p>
    </div>
  );
}

function EmptyConversations() {
  return (
    <div
      className="flex h-full flex-col items-center justify-center gap-2 px-6 py-12 text-center"
      data-testid="empty-conversations"
    >
      <MessageSquare className="h-8 w-8 text-white/20" />
      <p className="text-sm font-medium text-white/60">No conversations yet</p>
      <p className="text-xs text-white/40">
        Go to <span className="text-primary">/donors</span>, pick one, and we'll
        add a quick-send shortcut here next.
      </p>
    </div>
  );
}

function EmptyThread({ hasConversations }: { hasConversations: boolean }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <MessageSquare className="h-8 w-8 text-white/20" />
      <p className="text-sm font-medium text-white/60">
        {hasConversations
          ? "Select a conversation to view the thread"
          : "No conversations yet — start one from the right"}
      </p>
    </div>
  );
}

function LoadingRow() {
  return (
    <div className="flex items-center justify-center p-6">
      <Loader2 className="h-4 w-4 animate-spin text-white/40" />
    </div>
  );
}
