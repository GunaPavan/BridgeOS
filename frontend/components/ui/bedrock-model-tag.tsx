"use client";

import { Brain, Sparkles, Zap } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Compact pill identifying which Bedrock model handled a turn.
 *
 * Three families:
 *   - Sonnet (default chat — deep reasoning)        blue
 *   - Haiku  (intent classification — fast/cheap)   amber
 *   - Titan  (text embeddings — cohort memory)      violet
 *
 * Hover-only tooltip surfaces the full model id and routing task per
 * Module 1 plan (don't clutter the bubble — show on demand).
 */
type Family = "sonnet" | "haiku" | "titan" | "unknown";

function familyFor(modelId: string): Family {
  const id = modelId.toLowerCase();
  if (id.includes("sonnet")) return "sonnet";
  if (id.includes("haiku")) return "haiku";
  if (id.includes("titan")) return "titan";
  return "unknown";
}

const STYLE: Record<
  Family,
  { label: string; cls: string; Icon: typeof Sparkles }
> = {
  sonnet: {
    label: "Sonnet",
    cls: "border-sky-400/40 bg-sky-500/10 text-sky-200",
    Icon: Sparkles,
  },
  haiku: {
    label: "Haiku",
    cls: "border-amber-400/40 bg-amber-500/10 text-amber-200",
    Icon: Zap,
  },
  titan: {
    label: "Titan",
    cls: "border-violet-400/40 bg-violet-500/10 text-violet-200",
    Icon: Brain,
  },
  unknown: {
    label: "Bedrock",
    cls: "border-white/15 bg-white/5 text-white/60",
    Icon: Sparkles,
  },
};

export function BedrockModelTag({
  modelId,
  task,
  tokens,
}: {
  modelId: string;
  task?: string | null;
  tokens?: number | null;
}) {
  const family = familyFor(modelId);
  const { label, cls, Icon } = STYLE[family];

  // Tooltip title — native HTML tooltip is good enough for hackathon polish.
  const tooltipParts: string[] = [`Bedrock model: ${modelId}`];
  if (task) tooltipParts.push(`Task: ${task}`);
  if (typeof tokens === "number") tooltipParts.push(`${tokens} output tokens`);

  return (
    <span
      data-testid="bedrock-model-tag"
      data-family={family}
      data-task={task ?? "none"}
      title={tooltipParts.join("\n")}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
        cls,
      )}
    >
      <Icon className="h-2.5 w-2.5" />
      {label}
    </span>
  );
}
