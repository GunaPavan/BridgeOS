"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Cpu,
  Loader2,
  Mail,
  MessageSquare,
  Phone,
  Rocket,
  XCircle,
} from "lucide-react";
import type { ComponentType } from "react";

import {
  ChannelResult,
  DemoChannelKey,
  FireAllResponse,
  OutreachCopy,
  api,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * One-click demo: ping the presenter's phone (voice + WhatsApp + SMS) and
 * email inbox in parallel. Shows four live status tiles that fill in as the
 * backend response arrives — judges see a single button trigger a real
 * fan-out across every channel the production engine uses.
 *
 * Backend: POST /admin/demo/fire-all returns per-channel SID + status in
 * ~2 seconds (parallel ThreadPoolExecutor over Twilio / SNS / SES). The
 * voice call delivers a few seconds later via Twilio's network.
 */
export function DemoFireAllCard() {
  const { data: contacts } = useQuery({
    queryKey: ["demo-contacts"],
    queryFn: () => api.getDemoContacts(),
    staleTime: 60_000,
  });

  const fire = useMutation({
    mutationFn: () => api.fireAllDemoChannels(),
  });

  const channels: DemoChannelKey[] = ["voice", "whatsapp", "sms", "email"];
  const byChannel: Record<DemoChannelKey, ChannelResult | undefined> = {
    voice: undefined,
    whatsapp: undefined,
    sms: undefined,
    email: undefined,
  };
  if (fire.data) {
    for (const c of fire.data.channels) byChannel[c.channel] = c;
  }

  return (
    <section
      data-testid="demo-fire-all-card"
      className="mb-6 overflow-hidden rounded-2xl border border-primary/30 bg-gradient-to-br from-primary/15 via-primary/5 to-fuchsia-500/10 p-5"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="max-w-xl">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-primary/80">
            <Rocket className="h-3.5 w-3.5" />
            Live judge demo
          </div>
          <h2 className="mt-1 text-xl font-bold text-white">
            Fire every outbound channel from one click
          </h2>
          <p className="mt-1 text-sm text-white/65">
            Simulates a single allocator decision lighting up{" "}
            <span className="font-semibold text-white">voice</span>,{" "}
            <span className="font-semibold text-white">WhatsApp</span>,{" "}
            <span className="font-semibold text-white">SMS</span> and{" "}
            <span className="font-semibold text-white">email</span> in parallel.
            Same code paths as the real automation engine.
          </p>
          {contacts ? (
            <p className="mt-2 text-[11px] text-white/45">
              Pings{" "}
              <code className="rounded bg-black/30 px-1.5 py-0.5 text-white/70">
                {contacts.phone}
              </code>{" "}
              and{" "}
              <code className="rounded bg-black/30 px-1.5 py-0.5 text-white/70">
                {contacts.email}
              </code>
            </p>
          ) : null}
        </div>

        <button
          type="button"
          data-testid="demo-fire-all-button"
          onClick={() => fire.mutate()}
          disabled={fire.isPending}
          className={cn(
            "inline-flex items-center gap-2 rounded-xl border px-5 py-3 text-base font-semibold transition-all",
            "border-primary/50 bg-primary text-black shadow-lg shadow-primary/30 hover:bg-primary/90",
            "disabled:cursor-not-allowed disabled:opacity-60",
          )}
        >
          {fire.isPending ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" />
              Firing 4 channels…
            </>
          ) : (
            <>
              <Rocket className="h-5 w-5" />
              Fire all channels now
            </>
          )}
        </button>
      </div>

      {/* Result tiles — render in fixed order so the layout doesn't jump */}
      <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {channels.map((c) => (
          <ChannelTile
            key={c}
            channel={c}
            result={byChannel[c]}
            isPending={fire.isPending}
          />
        ))}
      </div>

      {/* LLM-composed copy — shown so judges see real Bedrock text */}
      {fire.data ? <CopyPanel copy={fire.data.copy} /> : null}

      {/* Context strip */}
      {fire.data ? <ContextStrip data={fire.data} /> : null}

      {fire.error ? (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">Fan-out failed.</p>
            <p className="mt-1 text-xs text-red-200/85">
              {(fire.error as Error).message}
            </p>
          </div>
        </div>
      ) : null}
    </section>
  );
}

// ---------------------------------------------------------------------------

const META: Record<
  DemoChannelKey,
  { label: string; Icon: ComponentType<{ className?: string }>; tint: string }
> = {
  voice: { label: "Voice (Twilio)", Icon: Phone, tint: "text-cyan-300" },
  whatsapp: { label: "WhatsApp (Twilio)", Icon: MessageSquare, tint: "text-emerald-300" },
  sms: { label: "SMS (AWS SNS)", Icon: MessageSquare, tint: "text-amber-300" },
  email: { label: "Email (AWS SES)", Icon: Mail, tint: "text-fuchsia-300" },
};

function ChannelTile({
  channel,
  result,
  isPending,
}: {
  channel: DemoChannelKey;
  result: ChannelResult | undefined;
  isPending: boolean;
}) {
  const meta = META[channel];
  const state = !result && isPending ? "firing" : !result ? "idle" : result.ok ? "ok" : "fail";

  const borderTone =
    state === "ok"
      ? "border-emerald-500/40 bg-emerald-500/5"
      : state === "fail"
        ? "border-red-500/40 bg-red-500/5"
        : state === "firing"
          ? "border-primary/30 bg-primary/5"
          : "border-white/10 bg-white/[0.03]";

  return (
    <div
      data-testid={`channel-tile-${channel}`}
      className={cn(
        "flex flex-col gap-2 rounded-xl border p-3 transition-colors",
        borderTone,
      )}
    >
      <div className="flex items-center justify-between">
        <div className={cn("flex items-center gap-1.5 text-xs", meta.tint)}>
          <meta.Icon className="h-3.5 w-3.5" />
          {meta.label}
        </div>
        <StateBadge state={state} />
      </div>

      {result ? (
        <>
          <p className="font-mono text-[11px] leading-tight text-white/70 break-all">
            {result.sid_or_message_id ?? "—"}
          </p>
          <div className="flex items-center justify-between text-[10px] text-white/45">
            <span>{result.status ?? "?"}</span>
            <span>{result.duration_ms} ms</span>
          </div>
          {result.is_mock ? (
            <p className="text-[10px] text-amber-300/80">⚠ mock (no live creds)</p>
          ) : null}
          {result.error ? (
            <p className="text-[10px] text-red-300/90 break-all">{result.error}</p>
          ) : null}
        </>
      ) : (
        <p className="text-[11px] text-white/35">
          {state === "firing" ? "queued…" : "click Fire to send"}
        </p>
      )}
    </div>
  );
}

function StateBadge({
  state,
}: {
  state: "idle" | "firing" | "ok" | "fail";
}) {
  if (state === "ok") return <CheckCircle2 className="h-4 w-4 text-emerald-400" />;
  if (state === "fail") return <XCircle className="h-4 w-4 text-red-400" />;
  if (state === "firing") return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
  return <span className="h-2 w-2 rounded-full bg-white/20" />;
}

function CopyPanel({ copy }: { copy: OutreachCopy }) {
  const isLive = copy.source === "bedrock" || copy.source === "anthropic";
  const sourceLabel =
    copy.source === "bedrock"
      ? "AWS Bedrock"
      : copy.source === "anthropic"
        ? "Anthropic API"
        : copy.source === "mock"
          ? "Mock (no creds)"
          : "Template fallback";
  return (
    <div className="mt-4 rounded-xl border border-white/10 bg-black/30 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/50">
          <Cpu className="h-3.5 w-3.5" />
          LLM-composed copy
        </div>
        <div
          className={cn(
            "flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-mono",
            isLive
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              : "border-amber-500/40 bg-amber-500/10 text-amber-300",
          )}
        >
          <span>{sourceLabel}</span>
          <span className="text-white/40">·</span>
          <span className="text-white/70">{copy.model}</span>
          {copy.tokens_in != null && copy.tokens_out != null ? (
            <>
              <span className="text-white/40">·</span>
              <span className="text-white/55">
                {copy.tokens_in}→{copy.tokens_out} tok
              </span>
            </>
          ) : null}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <CopySnippet label="Voice question (read by Polly Kajal)" text={copy.voice_question} />
        <CopySnippet label="WhatsApp body" text={copy.whatsapp_body} />
        <CopySnippet label="SMS body" text={copy.sms_body} />
        <CopySnippet
          label={`Email — ${copy.email_subject}`}
          text={copy.email_body}
          multiline
        />
      </div>
    </div>
  );
}

function CopySnippet({
  label,
  text,
  multiline,
}: {
  label: string;
  text: string;
  multiline?: boolean;
}) {
  return (
    <div className="rounded-lg border border-white/5 bg-white/[0.03] p-3">
      <p className="mb-1 text-[10px] uppercase tracking-wider text-white/40">{label}</p>
      <p
        className={cn(
          "text-xs leading-snug text-white/80",
          multiline ? "whitespace-pre-wrap" : "",
        )}
      >
        {text}
      </p>
    </div>
  );
}

function ContextStrip({ data }: { data: FireAllResponse }) {
  return (
    <div className="mt-4 rounded-xl border border-white/5 bg-black/20 p-3 text-xs text-white/65">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span>
          <span className="text-white/40">Donor</span>{" "}
          <span className="font-medium text-white">{data.context.donor_name}</span>
        </span>
        <span>
          <span className="text-white/40">Patient</span>{" "}
          <span className="font-medium text-white">{data.context.patient_name}</span>
        </span>
        <span>
          <span className="text-white/40">Total wall-clock</span>{" "}
          <span className="font-mono text-emerald-300">{data.total_duration_ms} ms</span>
        </span>
        <span>
          <span className="text-white/40">Ping</span>{" "}
          <code className="font-mono text-white/55">{data.context.ping_id.slice(0, 8)}…</code>
        </span>
      </div>
    </div>
  );
}
