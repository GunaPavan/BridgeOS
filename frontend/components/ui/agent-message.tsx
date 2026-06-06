"use client";

import { Sparkles, User } from "lucide-react";

import { BedrockModelTag } from "@/components/ui/bedrock-model-tag";
import { type AgentMessage as AgentMsg } from "@/lib/api";
import { cn } from "@/lib/utils";

/** A single chat bubble for the Care Agent. */
export function AgentMessageBubble({ message }: { message: AgentMsg }) {
  const isUser = message.role === "user";
  return (
    <div
      data-testid="agent-message"
      data-role={message.role}
      className={cn("flex gap-3", isUser ? "justify-end" : "justify-start")}
    >
      {!isUser ? (
        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/15">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
        </div>
      ) : null}
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-primary/15 text-white"
            : "bg-white/5 text-white/90",
        )}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {!isUser && message.provider === "bedrock" && message.model ? (
          <div className="mt-2 flex items-center gap-2 text-[10px] text-white/40">
            <BedrockModelTag
              modelId={message.model}
              task={message.task ?? null}
              tokens={message.tokens_out ?? null}
            />
            {message.tokens_out ? (
              <span>· {message.tokens_out} tok</span>
            ) : null}
          </div>
        ) : !isUser && message.provider ? (
          <div className="mt-2 flex items-center gap-2 text-[10px] text-white/40">
            <span className="rounded bg-white/5 px-1.5 py-0.5 font-mono">
              {message.provider}
            </span>
            {message.model ? (
              <span className="font-mono">{message.model}</span>
            ) : null}
            {message.tokens_out ? (
              <span>· {message.tokens_out} tok</span>
            ) : null}
          </div>
        ) : null}
      </div>
      {isUser ? (
        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/10">
          <User className="h-3.5 w-3.5 text-white/60" />
        </div>
      ) : null}
    </div>
  );
}
