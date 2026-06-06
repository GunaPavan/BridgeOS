"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Heart,
  Loader2,
  MessageSquareText,
  Send,
  Sparkles,
} from "lucide-react";

import { api, type CaregiverConversationThread, type NotifyCaregiverRequest } from "@/lib/api";
import { MessageBubble } from "@/components/ui/message-bubble";
import { useToast } from "@/components/ui/toast";
import { cn, formatDate } from "@/lib/utils";

const CAREGIVER_TEMPLATES: {
  key: NotifyCaregiverRequest["template_key"];
  label: string;
  hint: string;
}[] = [
  {
    key: "bridge_covered_caregiver",
    label: "Bridge covered",
    hint: "Reassurance — cohort is healthy for the next cycle",
  },
  {
    key: "recruit_success_caregiver",
    label: "Recruit success",
    hint: "A new donor just joined the cohort",
  },
  {
    key: "transfusion_confirmed_caregiver",
    label: "Transfusion confirmed",
    hint: "Next transfusion date is locked",
  },
];

/**
 * G5 — Caregiver communications panel for the patient profile page.
 * Shows recent caregiver messages + lets the coordinator fire a *_caregiver
 * template ad hoc.
 */
export function CaregiverPanel({
  patientId,
  caregiverName,
  caregiverPhone,
  caregiverRelation,
}: {
  patientId: string;
  caregiverName: string | null | undefined;
  caregiverPhone: string | null | undefined;
  caregiverRelation: string | null | undefined;
}) {
  const queryClient = useQueryClient();
  const { show } = useToast();
  const [selectedTemplate, setSelectedTemplate] = useState<
    NotifyCaregiverRequest["template_key"]
  >("bridge_covered_caregiver");

  const threadQuery = useQuery({
    queryKey: ["caregiver-thread", patientId],
    queryFn: () => api.getCaregiverThread(patientId),
    enabled: !!caregiverName && !!caregiverPhone,
    refetchInterval: 8000,
    staleTime: 5000,
  });

  const sendMutation = useMutation({
    mutationFn: () =>
      api.notifyCaregiver(patientId, { template_key: selectedTemplate }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["caregiver-thread", patientId] });
      queryClient.invalidateQueries({ queryKey: ["whatsapp", "conversations"] });
      show({
        title: `Caregiver notified`,
        description:
          (data.language_used ? `[${data.language_used}] ` : "") +
          (data.body ?? "").slice(0, 90),
        variant: "success",
      });
    },
    onError: (err: Error) => {
      show({
        title: "Caregiver send failed",
        description: err.message || "Try again in a moment.",
        variant: "error",
      });
    },
  });

  if (!caregiverName || !caregiverPhone) {
    return (
      <section
        data-testid="caregiver-panel-empty"
        className="rounded-xl border border-white/5 bg-surface/30 p-4"
      >
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
          <Heart className="h-3 w-3" />
          Caregiver communications
        </div>
        <p className="mt-2 text-sm text-white/55">
          No caregiver configured. Add a caregiver phone in patient settings to
          enable WhatsApp updates.
        </p>
      </section>
    );
  }

  const messages = threadQuery.data?.messages ?? [];

  return (
    <section
      data-testid="caregiver-panel"
      className="rounded-xl border border-white/5 bg-surface/40 p-4"
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Heart className="h-3 w-3 text-primary" />
            Caregiver communications
          </div>
          <p className="mt-1 text-sm font-semibold text-white">
            {caregiverName}
            {caregiverRelation ? (
              <span className="ml-2 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] uppercase tracking-wider text-white/55">
                {caregiverRelation}
              </span>
            ) : null}
          </p>
          <p className="text-[11px] font-mono text-white/40">{caregiverPhone}</p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <select
            data-testid="caregiver-template-select"
            value={selectedTemplate}
            onChange={(e) =>
              setSelectedTemplate(
                e.target.value as NotifyCaregiverRequest["template_key"],
              )
            }
            disabled={sendMutation.isPending}
            className="rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-xs text-white disabled:opacity-50"
          >
            {CAREGIVER_TEMPLATES.map((t) => (
              <option key={t.key} value={t.key}>
                {t.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => sendMutation.mutate()}
            disabled={sendMutation.isPending}
            data-testid="caregiver-send"
            className="inline-flex items-center gap-1.5 rounded-md bg-primary/15 px-2.5 py-1 text-xs font-medium text-primary ring-1 ring-primary/30 transition-colors hover:bg-primary/25 disabled:opacity-50"
          >
            {sendMutation.isPending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Send className="h-3 w-3" />
            )}
            Notify
          </button>
        </div>
      </div>

      {/* Recent messages thread (most recent at bottom) */}
      {messages.length === 0 ? (
        <p className="rounded-md border border-white/5 bg-black/20 p-3 text-xs text-white/40">
          No caregiver messages yet. Use the dropdown above to send the first one.
        </p>
      ) : (
        <div
          data-testid="caregiver-thread"
          className="max-h-72 space-y-2 overflow-y-auto"
        >
          {messages.slice(-5).map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
        </div>
      )}
    </section>
  );
}
