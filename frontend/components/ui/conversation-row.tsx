"use client";

import { Heart } from "lucide-react";

import { type ConversationSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * A row in the conversations sidebar. G5 added a `kind` discriminator so the
 * same list can show both donor rows (existing) and caregiver rows (new).
 */
export function ConversationRow({
  conversation,
  selected,
  onSelect,
}: {
  conversation: ConversationSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  const { kind, donor, caregiver, last_message, message_count } = conversation;

  if (kind === "caregiver" && caregiver) {
    return (
      <li>
        <button
          type="button"
          onClick={onSelect}
          data-testid="conversation-row"
          data-kind="caregiver"
          data-patient-id={caregiver.patient_id}
          className={cn(
            "flex w-full flex-col items-start gap-1 border-b border-white/5 px-4 py-3 text-left transition-colors",
            selected ? "bg-primary/10" : "hover:bg-white/[0.03]",
          )}
        >
          <div className="flex w-full items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 truncate text-sm font-medium text-white">
              <Heart className="h-3 w-3 shrink-0 text-primary" />
              {caregiver.caregiver_name}
            </span>
            <span className="rounded bg-accent/15 px-1.5 py-0.5 font-mono text-[10px] text-accent">
              caregiver
            </span>
          </div>
          <p className="w-full truncate text-xs text-white/50">
            {last_message.body}
          </p>
          <div className="flex items-center gap-2 text-[10px] text-white/30">
            <span>
              {message_count} msg{message_count === 1 ? "" : "s"}
            </span>
            <span>·</span>
            <span>
              {caregiver.caregiver_relation ?? "caregiver"} of{" "}
              {caregiver.patient_name}
            </span>
          </div>
        </button>
      </li>
    );
  }

  // Donor row (existing behaviour)
  if (!donor) return null;
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        data-testid="conversation-row"
        data-kind="donor"
        data-donor-id={donor.id}
        className={cn(
          "flex w-full flex-col items-start gap-1 border-b border-white/5 px-4 py-3 text-left transition-colors",
          selected ? "bg-primary/10" : "hover:bg-white/[0.03]",
        )}
      >
        <div className="flex w-full items-center justify-between gap-2">
          <span className="truncate text-sm font-medium text-white">
            {donor.name}
          </span>
          <span className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-primary">
            {donor.blood_group}
          </span>
        </div>
        <p className="w-full truncate text-xs text-white/50">
          {last_message.body}
        </p>
        <div className="flex items-center gap-2 text-[10px] text-white/30">
          <span>
            {message_count} msg{message_count === 1 ? "" : "s"}
          </span>
          <span>·</span>
          <span>{donor.city}</span>
        </div>
      </button>
    </li>
  );
}
