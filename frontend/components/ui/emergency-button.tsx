"use client";

import { useMutation } from "@tanstack/react-query";
import { AlertOctagon, CheckCircle2, Loader2, Siren, X } from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * EMERGENCY OUTREACH — the big red button.
 *
 * Coordinator-only action: fires a broadcast wave to every donor who can
 * physically reach the hospital before the transfusion deadline. Social
 * cooldowns + quiet hours are waived; clinical 90-day deferral is NEVER
 * waived. The confirm dialog requires coordinator name + reason for the
 * audit log.
 */
export function EmergencyButton({
  patientId,
  patientName,
}: {
  patientId: string;
  patientName: string;
}) {
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<{
    event_id: string;
    wave_id: string | null;
    reachable_count: number;
    pool_size_before_filter: number;
  } | null>(null);

  const close = () => {
    setOpen(false);
    setResult(null);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        data-testid="emergency-button"
        className="inline-flex items-center gap-2 rounded-lg border border-red-500/60 bg-red-500/15 px-4 py-2 text-sm font-semibold text-red-200 transition hover:border-red-400 hover:bg-red-500/25"
      >
        <Siren className="h-4 w-4" />
        EMERGENCY OUTREACH
      </button>

      {open ? (
        <EmergencyDialog
          patientId={patientId}
          patientName={patientName}
          result={result}
          setResult={setResult}
          onClose={close}
        />
      ) : null}
    </>
  );
}

function EmergencyDialog({
  patientId,
  patientName,
  result,
  setResult,
  onClose,
}: {
  patientId: string;
  patientName: string;
  result: {
    event_id: string;
    wave_id: string | null;
    reachable_count: number;
    pool_size_before_filter: number;
  } | null;
  setResult: (r: {
    event_id: string;
    wave_id: string | null;
    reachable_count: number;
    pool_size_before_filter: number;
  } | null) => void;
  onClose: () => void;
}) {
  const [coordinator, setCoordinator] = useState("");
  const [hours, setHours] = useState(2);
  const [justification, setJustification] = useState("");
  const [error, setError] = useState<string | null>(null);

  const trigger = useMutation({
    mutationFn: async () => {
      const deadline = new Date(Date.now() + hours * 60 * 60 * 1000);
      return api.triggerEmergency({
        patientId,
        coordinatorName: coordinator,
        deadlineIso: deadline.toISOString(),
        justification,
      });
    },
    onSuccess: (r) => {
      setResult(r);
      setError(null);
    },
    onError: (e: Error) => setError(e.message),
  });

  const disabled = coordinator.length < 1 || justification.length < 1 || trigger.isPending;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      data-testid="emergency-dialog"
    >
      <div className="mx-4 w-full max-w-lg rounded-2xl border border-red-500/40 bg-surface p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2 text-red-300">
            <AlertOctagon className="h-5 w-5" />
            <h2 className="text-lg font-semibold">EMERGENCY OUTREACH</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-white/40 hover:bg-white/5 hover:text-white"
            data-testid="close-emergency"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {result ? (
          <div data-testid="emergency-success" className="space-y-3">
            <div className="flex items-center gap-2 text-emerald-300">
              <CheckCircle2 className="h-5 w-5" />
              <p className="text-sm font-semibold">Event logged · wave created</p>
            </div>
            <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm text-white/70">
              <p>
                Patient <span className="text-white">{patientName}</span> ·{" "}
                <span className="font-mono text-xs text-white/40">
                  {result.event_id.slice(0, 8)}
                </span>
              </p>
              <p className="mt-1">
                Reachable donors:{" "}
                <span
                  className="font-mono text-emerald-300"
                  data-testid="reachable-count"
                >
                  {result.reachable_count}
                </span>{" "}
                of {result.pool_size_before_filter} active in pool
              </p>
              {result.wave_id ? (
                <p className="mt-1 text-xs text-white/40">
                  Wave id <span className="font-mono">{result.wave_id.slice(0, 8)}</span> — dispatch with{" "}
                  <span className="font-mono text-white/70">
                    POST /outreach/waves/{result.wave_id.slice(0, 8)}…/dispatch?override_quiet_hours=true
                  </span>
                </p>
              ) : (
                <p className="mt-1 text-xs text-amber-300">
                  Zero reachable donors — escalate to eRaktKosh + hospital bank now.
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={onClose}
              className="w-full rounded-lg border border-white/10 bg-white/5 py-2 text-sm text-white/80 hover:bg-white/10"
            >
              Close
            </button>
          </div>
        ) : (
          <>
            <p className="mb-4 text-sm text-white/70">
              Broadcast WhatsApp to every donor who can physically reach{" "}
              <span className="text-white">{patientName}&apos;s</span> hospital
              before the deadline. Social cooldowns + quiet hours are waived
              for this call. 90-day clinical deferral is NEVER waived.
            </p>

            <div className="space-y-3">
              <div>
                <label className="text-xs uppercase tracking-wider text-white/40">
                  Coordinator name (audit log)
                </label>
                <input
                  type="text"
                  data-testid="emergency-coordinator"
                  value={coordinator}
                  onChange={(e) => setCoordinator(e.target.value)}
                  className="mt-1 w-full rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-400/50"
                  placeholder="Your name"
                />
              </div>

              <div>
                <label className="text-xs uppercase tracking-wider text-white/40">
                  Transfusion deadline (hours from now)
                </label>
                <input
                  type="number"
                  data-testid="emergency-hours"
                  min={1}
                  max={48}
                  value={hours}
                  onChange={(e) => setHours(Number(e.target.value) || 1)}
                  className="mt-1 w-full rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-400/50"
                />
              </div>

              <div>
                <label className="text-xs uppercase tracking-wider text-white/40">
                  Justification
                </label>
                <textarea
                  data-testid="emergency-justification"
                  value={justification}
                  onChange={(e) => setJustification(e.target.value)}
                  rows={3}
                  className="mt-1 w-full rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-red-400/50"
                  placeholder="e.g. Patient at Apollo with severe Hb drop — needs B+ within 4 hours."
                />
              </div>

              {error ? (
                <div className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
                  {error}
                </div>
              ) : null}

              <button
                type="button"
                onClick={() => trigger.mutate()}
                disabled={disabled}
                data-testid="emergency-confirm"
                className={cn(
                  "w-full rounded-lg border border-red-500/60 bg-red-500/20 py-3 text-sm font-semibold text-red-200 transition",
                  disabled
                    ? "cursor-not-allowed opacity-50"
                    : "hover:border-red-400 hover:bg-red-500/30",
                )}
              >
                {trigger.isPending ? (
                  <span className="inline-flex items-center gap-2">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> Triggering…
                  </span>
                ) : (
                  "Trigger emergency outreach"
                )}
              </button>
              <p className="text-[10px] text-white/40">
                A signed audit row is created on every trigger. Misuse is tracked.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
