"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CheckCircle2,
  Clock,
  Loader2,
  MapPin,
  Network,
  ShieldCheck,
  Sparkles,
  UserPlus,
} from "lucide-react";

import {
  api,
  type BridgeRecommendation,
  type RecruitmentCandidate,
  type WeakDonor,
} from "@/lib/api";
import {
  RecruitConfirmModal,
  type RecruitLanguage,
} from "@/components/ui/recruit-confirm-modal";
import { useToast } from "@/components/ui/toast";
import { cn, displayOr, isMissing } from "@/lib/utils";

const URGENCY_STYLES: Record<
  BridgeRecommendation["urgency"],
  { pill: string; label: string }
> = {
  critical: {
    pill: "border-red-500/40 bg-red-500/15 text-red-300",
    label: "Critical",
  },
  high: {
    pill: "border-amber-500/40 bg-amber-500/15 text-amber-300",
    label: "High",
  },
  medium: {
    pill: "border-blue-500/40 bg-blue-500/15 text-blue-300",
    label: "Medium",
  },
};

export function RecommendationCard({
  rec,
  onRecruited,
}: {
  rec: BridgeRecommendation;
  onRecruited?: () => void;
}) {
  const urgency = URGENCY_STYLES[rec.urgency];

  // One query per card (not per candidate row). With 40+ cards on /recommendations,
  // we must be gentle on the polling cadence — and explicitly opt out of refetching
  // on window focus so Playwright's auto-stability check doesn't see flickering rows.
  const pendingQuery = useQuery({
    queryKey: ["pending-recruits", rec.bridge_id],
    queryFn: () => api.listPendingRecruits(rec.bridge_id),
    refetchInterval: 15000,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    staleTime: 10000,
  });
  const pendingByDonorId = new Map(
    (pendingQuery.data ?? []).map((p) => [p.candidate_donor_id, p] as const),
  );

  return (
    <article
      className="rounded-xl border border-white/10 bg-surface/40 p-5"
      data-testid="recommendation-card"
      data-bridge-id={rec.bridge_id}
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
            <Network className="h-3 w-3" />
            {rec.bridge_name}
          </div>
          <h3 className="mt-1 text-lg font-semibold text-white">
            {rec.patient_name}
          </h3>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-white/60">
            <span className="rounded bg-white/5 px-2 py-0.5 font-mono text-primary">
              {rec.patient_blood_group}
            </span>
            <span>{rec.patient_age} yrs</span>
            {!isMissing(rec.patient_hospital) && (
              <>
                <span className="text-white/30">·</span>
                <Building2 className="h-3 w-3" /> {displayOr(rec.patient_hospital)}
              </>
            )}
            <span className="text-white/30">·</span>
            <MapPin className="h-3 w-3" /> {displayOr(rec.patient_city)}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "rounded-full border px-3 py-0.5 text-xs uppercase tracking-wider",
              urgency.pill,
            )}
            data-testid="urgency-pill"
          >
            {urgency.label}
          </span>
          <Link
            href={`/bridges/${rec.bridge_id}`}
            className="text-xs text-white/50 hover:text-white"
          >
            View bridge ↗
          </Link>
        </div>
      </header>

      {/* Weak donors */}
      {rec.weak_donors.length > 0 ? (
        <div className="mt-4 rounded-lg border border-red-500/20 bg-red-500/5 p-3">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-red-300/80">
            <AlertTriangle className="h-3 w-3" />
            At-risk donors ({rec.weak_donors.length})
          </div>
          <ul className="mt-2 space-y-1.5">
            {rec.weak_donors.map((w) => (
              <WeakDonorRow key={w.membership_id} weak={w} />
            ))}
          </ul>
        </div>
      ) : (
        <div className="mt-4 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-xs text-emerald-300/80">
          <CheckCircle2 className="mr-1 inline h-3 w-3" /> No at-risk donors —
          showing strengthen-cohort suggestions
        </div>
      )}

      {/* Candidates */}
      <div className="mt-4 space-y-2">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/40">
          <Sparkles className="h-3 w-3" />
          Recommended candidates ({rec.candidates.length})
        </div>
        {rec.candidates.length === 0 ? (
          <p className="text-xs text-white/40">
            No compatible candidates outside the current cohort.
          </p>
        ) : (
          <ul className="space-y-2">
            {rec.candidates.map((c) => (
              <CandidateRow
                key={c.donor.id}
                candidate={c}
                bridgeId={rec.bridge_id}
                patientName={rec.patient_name}
                replaceDonorId={rec.weak_donors[0]?.donor_id ?? null}
                replaceDonorName={rec.weak_donors[0]?.donor_name ?? null}
                pendingForCandidate={pendingByDonorId.get(c.donor.id) ?? null}
                onRecruited={onRecruited}
              />
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}

function WeakDonorRow({ weak }: { weak: WeakDonor }) {
  // Fetch the multi-class churn prediction for this donor so the inbox
  // shows the recommended ACTION, not just a risk number.
  const churnQ = useQuery({
    queryKey: ["donor-churn", weak.donor_id],
    queryFn: () => api.getChurnPrediction(weak.donor_id),
    staleTime: 60_000,
    retry: false,
  });

  const cls = churnQ.data?.predicted_class;
  const cls_pill =
    cls === "active"
      ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-200"
      : cls === "inactive_not_donated_1y"
      ? "border-amber-400/30 bg-amber-500/10 text-amber-200"
      : cls === "inactive_limited_despite_calls"
      ? "border-red-400/30 bg-red-500/10 text-red-200"
      : "border-white/10 bg-white/5 text-white/40";
  const cls_short =
    cls === "active"
      ? "Active"
      : cls === "inactive_not_donated_1y"
      ? "Not donated 1Y"
      : cls === "inactive_limited_despite_calls"
      ? "Limited"
      : "—";

  return (
    <li
      data-testid="weak-donor-row"
      data-predicted-class={cls ?? "loading"}
      className="rounded-md bg-black/15 p-2"
    >
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="text-white/85">{weak.donor_name}</span>
        <div className="flex items-center gap-2">
          {cls ? (
            <span
              className={`rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${cls_pill}`}
              title={churnQ.data?.recommended_action}
            >
              {cls_short}
            </span>
          ) : null}
          <span className="font-mono text-xs text-red-300">
            {Math.round(weak.churn_90d * 100)}% churn
          </span>
        </div>
      </div>
      {churnQ.data?.recommended_action ? (
        <p className="mt-1 text-[11px] text-white/55">
          → {churnQ.data.recommended_action}
        </p>
      ) : null}
    </li>
  );
}

function CandidateRow({
  candidate,
  bridgeId,
  patientName,
  replaceDonorId,
  replaceDonorName,
  pendingForCandidate,
  onRecruited,
}: {
  candidate: RecruitmentCandidate;
  bridgeId: string;
  patientName: string;
  replaceDonorId: string | null;
  replaceDonorName: string | null;
  pendingForCandidate: import("@/lib/api").PendingRecruit | null;
  onRecruited?: () => void;
}) {
  const queryClient = useQueryClient();
  const { show } = useToast();
  const [modalOpen, setModalOpen] = useState(false);

  const recruit = useMutation({
    mutationFn: (language: RecruitLanguage) =>
      api.recruit(bridgeId, {
        candidate_donor_id: candidate.donor.id,
        replace_donor_id: replaceDonorId,
        language,
      }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      queryClient.invalidateQueries({ queryKey: ["bridge", bridgeId] });
      queryClient.invalidateQueries({ queryKey: ["stability", bridgeId] });
      queryClient.invalidateQueries({ queryKey: ["schedule", bridgeId] });
      queryClient.invalidateQueries({ queryKey: ["pending-recruits", bridgeId] });
      setModalOpen(false);
      show({
        title: `Invite sent to ${data.added_donor_name}`,
        description: replaceDonorName
          ? `Waiting on YES — will replace ${replaceDonorName} once they confirm.`
          : `Waiting on YES — joins the bridge once they confirm.`,
        variant: "success",
      });
      onRecruited?.();
    },
    onError: (err: Error) => {
      show({
        title: "Recruit failed",
        description: err.message || "Try again in a moment.",
        variant: "error",
      });
    },
  });

  const churnPct = Math.round(candidate.predicted_churn_90d * 100);
  const responsePct = Math.round(candidate.donor.response_rate * 100);

  return (
    <li
      className="rounded-lg border border-white/5 bg-black/20 p-3"
      data-testid="candidate-row"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <p className="font-medium text-white">{candidate.donor.name}</p>
            {candidate.donor.kell_negative ? (
              <ShieldCheck
                className="h-3.5 w-3.5 text-accent"
                aria-label="Kell-negative match"
              />
            ) : null}
          </div>
          <p className="text-xs text-white/50">
            {candidate.donor.age} · {candidate.donor.city} ·{" "}
            <span className="font-mono">{candidate.donor.blood_group}</span>
          </p>
        </div>
        <div className="text-right text-xs">
          <p className="text-white/40">Match score</p>
          <p className="font-mono text-base font-semibold text-emerald-300">
            {Math.round(candidate.composite_score * 100)}
          </p>
        </div>
      </div>

      <div className="mt-2 grid grid-cols-3 gap-2 text-[11px] text-white/60">
        <span>{candidate.distance_km.toFixed(1)} km</span>
        <span>{responsePct}% response</span>
        <span className={cn(churnPct >= 40 && "text-amber-300")}>
          {churnPct}% predicted churn
        </span>
      </div>

      {candidate.rationale.length > 0 ? (
        <ul className="mt-2 space-y-0.5 text-[11px] text-white/50">
          {candidate.rationale.slice(0, 4).map((r) => (
            <li key={r.factor}>· {r.description}</li>
          ))}
        </ul>
      ) : null}

      <div className="mt-3 flex items-center justify-between gap-2">
        <p className="text-[11px] text-white/40">
          {replaceDonorName ? (
            <>
              Replaces <span className="text-white/60">{replaceDonorName}</span>
            </>
          ) : (
            <>Adds to cohort</>
          )}
        </p>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          disabled={
            recruit.isPending || recruit.isSuccess || !!pendingForCandidate
          }
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-all",
            pendingForCandidate
              ? "border-amber-500/50 bg-amber-500/15 text-amber-200"
              : recruit.isSuccess
              ? "border-emerald-500/50 bg-emerald-500/20 text-emerald-200"
              : "border-primary/40 bg-primary/15 text-primary hover:bg-primary/25 disabled:opacity-50",
          )}
          data-testid="recruit-button"
          data-pending={pendingForCandidate ? "true" : "false"}
        >
          {pendingForCandidate ? (
            <>
              <Clock className="h-3 w-3" />
              Waiting on reply
            </>
          ) : recruit.isPending ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" />
              Sending invite…
            </>
          ) : recruit.isSuccess ? (
            <>
              <CheckCircle2 className="h-3 w-3" />
              Invite sent
            </>
          ) : (
            <>
              <UserPlus className="h-3 w-3" />
              Recruit
              <ArrowRight className="h-3 w-3" />
            </>
          )}
        </button>
      </div>
      {recruit.error ? (
        <p className="mt-1 text-[11px] text-red-300">
          {recruit.error.message}
        </p>
      ) : null}

      <RecruitConfirmModal
        open={modalOpen}
        candidateName={candidate.donor.name}
        candidateLanguage={
          (candidate.donor as { preferred_language?: RecruitLanguage })
            .preferred_language ?? "en"
        }
        replaceDonorName={replaceDonorName}
        patientName={patientName}
        isSubmitting={recruit.isPending}
        onCancel={() => !recruit.isPending && setModalOpen(false)}
        onConfirm={(language) => recruit.mutate(language)}
      />
    </li>
  );
}
