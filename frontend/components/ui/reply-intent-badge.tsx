import { cn } from "@/lib/utils";

export type ReplyIntentValue =
  | "accept"
  | "decline"
  | "reschedule_request"
  | "out_of_town"
  | "medical_defer"
  | "unrelated_question"
  | "stop"
  | "unknown";

const STYLES: Record<ReplyIntentValue, { label: string; cls: string }> = {
  accept: {
    label: "Accept",
    cls: "border-emerald-500/40 bg-emerald-500/15 text-emerald-300",
  },
  decline: {
    label: "Decline",
    cls: "border-red-500/40 bg-red-500/15 text-red-300",
  },
  reschedule_request: {
    label: "Reschedule",
    cls: "border-sky-500/40 bg-sky-500/15 text-sky-300",
  },
  out_of_town: {
    label: "Out of town",
    cls: "border-amber-500/40 bg-amber-500/15 text-amber-300",
  },
  medical_defer: {
    label: "Medical defer",
    cls: "border-violet-500/40 bg-violet-500/15 text-violet-300",
  },
  unrelated_question: {
    label: "Question",
    cls: "border-blue-500/40 bg-blue-500/15 text-blue-300",
  },
  stop: {
    label: "Opt-out",
    cls: "border-zinc-500/40 bg-zinc-500/15 text-zinc-300",
  },
  unknown: {
    label: "Unknown",
    cls: "border-white/10 bg-white/5 text-white/50",
  },
};

export function ReplyIntentBadge({
  intent,
  className,
}: {
  intent: ReplyIntentValue;
  className?: string;
}) {
  const meta = STYLES[intent] ?? STYLES.unknown;
  return (
    <span
      data-testid="reply-intent-badge"
      data-intent={intent}
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
        meta.cls,
        className,
      )}
    >
      {meta.label}
    </span>
  );
}
