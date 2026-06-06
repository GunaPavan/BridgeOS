"use client";

import { AlertCircle, CheckCheck, CheckCircle2, Globe } from "lucide-react";

import { type WhatsAppMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * A single WhatsApp message bubble — outbound (right, primary tint) or
 * inbound (left, neutral). Outbound bubbles show delivery status + template tag.
 */
export function MessageBubble({ message }: { message: WhatsAppMessage }) {
  const isOutbound = message.direction === "outbound";
  return (
    <div
      className={cn(
        "max-w-[80%] rounded-lg px-3 py-2 text-sm leading-snug",
        isOutbound
          ? "ml-auto bg-primary/15 text-white"
          : "mr-auto bg-white/5 text-white/90",
      )}
      data-testid="message-bubble"
      data-direction={message.direction}
    >
      <p className="whitespace-pre-wrap">{message.body}</p>
      <div className="mt-1 flex flex-wrap items-center gap-1 text-[10px] text-white/40">
        <span>{new Date(message.created_at).toLocaleTimeString()}</span>
        {isOutbound ? (
          <>
            <span>·</span>
            <StatusIcon status={message.status} />
            <span>{message.status}</span>
            {message.template_key ? (
              <>
                <span>·</span>
                <span className="rounded bg-white/5 px-1 font-mono">
                  {message.template_key}
                </span>
              </>
            ) : null}
            {message.language ? (
              <>
                <span>·</span>
                <span
                  data-testid="message-language-chip"
                  className="inline-flex items-center gap-0.5 rounded bg-accent/15 px-1 font-mono text-accent"
                >
                  <Globe className="h-2 w-2" />
                  {message.language}
                </span>
              </>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}

function StatusIcon({ status }: { status: WhatsAppMessage["status"] }) {
  if (status === "delivered" || status === "read") {
    return <CheckCheck className="h-3 w-3 text-emerald-300" />;
  }
  if (status === "sent" || status === "mocked" || status === "queued") {
    return <CheckCircle2 className="h-3 w-3 text-white/40" />;
  }
  if (status === "failed") {
    return <AlertCircle className="h-3 w-3 text-red-300" />;
  }
  return null;
}
