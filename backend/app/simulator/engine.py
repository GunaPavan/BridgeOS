"""Stateless simulation engine.

`compute_scenario()` takes:
  - the bridge (ORM, with patient + memberships + donors eagerly loaded)
  - the donor pool
  - a list of ejected donor IDs
and returns the baseline state, the post-action state, and a delta.

It runs the stability model, the rotation scheduler, and the recommender
engine over the in-memory modified cohort — **no database writes**. This is
called from the `/simulator` endpoint to power the interactive demo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable
from uuid import UUID

from app.ml.scheduler.solver import DonorInput, ScheduleResult, solve_rotation
from app.ml.stability import StabilityPredictor, extract_features
from app.ml.utils import haversine_km
from app.models import (
    Bridge,
    BridgeMembership,
    Donor,
    MembershipStatus,
)
from app.recommender.engine import (
    AT_RISK_CHURN_THRESHOLD,
    BridgeRecommendation,
    Candidate,
    WeakDonor,
    _can_donate_to,
    _days_until_eligible,
    _rationale,
    _score_candidate,
    _urgency_label,
)


@dataclass(frozen=True)
class Scenario:
    """The actions the user wants to simulate."""

    ejected_donor_ids: list[UUID] = field(default_factory=list)


@dataclass(frozen=True)
class CohortMemberState:
    donor_id: UUID
    donor_name: str
    blood_group: str
    churn_30d: float
    churn_60d: float
    churn_90d: float


@dataclass(frozen=True)
class ScenarioState:
    """The outcome of one (baseline or post-action) configuration."""

    active_donor_count: int
    cohort: list[CohortMemberState]
    avg_churn_90d: float
    max_churn_90d: float
    at_risk_count: int
    schedule_status: str
    schedule_slots_count: int
    schedule_objective: float
    schedule_solve_time_ms: int
    weak_donors: list[WeakDonor]
    top_candidates: list[Candidate]


@dataclass(frozen=True)
class ScenarioDelta:
    cohort_size_change: int
    avg_churn_change: float
    at_risk_change: int
    schedule_slots_change: int
    schedule_objective_change: float


@dataclass(frozen=True)
class ScenarioOutcome:
    bridge_id: UUID
    bridge_name: str
    today: date
    requested: Scenario
    baseline: ScenarioState
    scenario: ScenarioState
    delta: ScenarioDelta


# ---------- helpers ----------


def _build_donor_inputs(
    donors: Iterable[Donor], patient_lat: float, patient_lng: float
) -> list[DonorInput]:
    return [
        DonorInput(
            donor_id=d.id,
            name=d.name,
            blood_group=str(d.blood_group),
            last_donation_date=d.last_donation_date,
            response_rate=float(d.response_rate),
            distance_km=haversine_km(d.lat, d.lng, patient_lat, patient_lng),
        )
        for d in donors
    ]


def _evaluate(
    bridge: Bridge,
    active_donors: list[Donor],
    candidate_pool: list[Donor],
    predictor: StabilityPredictor,
    today: date,
    *,
    at_risk_threshold: float,
    top_k_candidates: int,
) -> ScenarioState:
    """Run stability + scheduler + recommender over the supplied active cohort.

    `active_donors` is the in-memory cohort (after any ejections applied).
    `candidate_pool` is the full donor table; we filter inside.
    """
    patient = bridge.patient

    # --- Stability ---
    member_features = [extract_features(d, bridge, today) for d in active_donors]
    member_preds = (
        predictor.predict_batch(member_features) if member_features else []
    )
    cohort_state = [
        CohortMemberState(
            donor_id=d.id,
            donor_name=d.name,
            blood_group=str(d.blood_group),
            churn_30d=p.churn_30d,
            churn_60d=p.churn_60d,
            churn_90d=p.churn_90d,
        )
        for d, p in zip(active_donors, member_preds)
    ]
    weak_donors_list: list[WeakDonor] = []
    for member, pred in zip(active_donors, member_preds):
        if pred.churn_90d >= at_risk_threshold:
            # Wrap into a synthetic membership-like object only as needed by WeakDonor.
            membership = next(
                (m for m in bridge.memberships if m.donor_id == member.id),
                None,
            )
            if membership is not None:
                weak_donors_list.append(
                    WeakDonor(
                        membership=membership,
                        churn_90d=pred.churn_90d,
                        top_factors=pred.top_factors,
                    )
                )
    weak_donors_list.sort(key=lambda w: w.churn_90d, reverse=True)

    avg_90 = (
        sum(c.churn_90d for c in cohort_state) / len(cohort_state)
        if cohort_state
        else 0.0
    )
    max_90 = max((c.churn_90d for c in cohort_state), default=0.0)
    at_risk = sum(1 for c in cohort_state if c.churn_90d >= at_risk_threshold)

    # --- Schedule ---
    donor_inputs = _build_donor_inputs(active_donors, patient.lat, patient.lng)
    sched: ScheduleResult = solve_rotation(
        donors=donor_inputs,
        last_transfusion_date=patient.last_transfusion_date,
        cadence_days=patient.transfusion_cadence_days,
        today=today,
        horizon_days=365,
        time_limit_seconds=3.0,
    )

    # --- Candidates (donors not in active cohort) ---
    active_ids = {d.id for d in active_donors}
    eligible_candidates = [
        d
        for d in candidate_pool
        if d.id not in active_ids
        and d.is_active
        and _can_donate_to(d.blood_group, patient.blood_group)
        and (not patient.kell_negative or d.kell_negative)
    ]
    scored_candidates: list[Candidate] = []
    if eligible_candidates:
        cand_features = [extract_features(d, bridge, today) for d in eligible_candidates]
        cand_preds = predictor.predict_batch(cand_features)
        for donor, pred in zip(eligible_candidates, cand_preds):
            distance = haversine_km(
                donor.lat, donor.lng, patient.lat, patient.lng
            )
            score = _score_candidate(donor, patient, pred.churn_90d, distance)
            scored_candidates.append(
                Candidate(
                    donor=donor,
                    composite_score=score,
                    distance_km=distance,
                    predicted_churn_90d=pred.churn_90d,
                    days_until_eligible=_days_until_eligible(donor, today),
                    rationale=_rationale(
                        donor,
                        patient,
                        distance,
                        pred.churn_90d,
                        _days_until_eligible(donor, today),
                    ),
                )
            )
        scored_candidates.sort(key=lambda c: c.composite_score, reverse=True)
    top = scored_candidates[:top_k_candidates]

    return ScenarioState(
        active_donor_count=len(active_donors),
        cohort=cohort_state,
        avg_churn_90d=avg_90,
        max_churn_90d=max_90,
        at_risk_count=at_risk,
        schedule_status=sched.status.value,
        schedule_slots_count=len(sched.slots),
        schedule_objective=sched.objective_value,
        schedule_solve_time_ms=sched.solve_time_ms,
        weak_donors=weak_donors_list,
        top_candidates=top,
    )


# ---------- public API ----------


def compute_scenario(
    bridge: Bridge,
    candidate_pool: list[Donor],
    predictor: StabilityPredictor,
    today: date,
    scenario: Scenario,
    *,
    at_risk_threshold: float = AT_RISK_CHURN_THRESHOLD,
    top_k_candidates: int = 3,
) -> ScenarioOutcome:
    """Compute baseline + scenario state for this bridge with no DB writes."""
    all_active_donors = [
        m.donor for m in bridge.memberships if m.status == MembershipStatus.ACTIVE
    ]

    # --- Baseline (no ejections) ---
    baseline = _evaluate(
        bridge,
        active_donors=all_active_donors,
        candidate_pool=candidate_pool,
        predictor=predictor,
        today=today,
        at_risk_threshold=at_risk_threshold,
        top_k_candidates=top_k_candidates,
    )

    # --- Scenario (with ejections) ---
    ejected = set(scenario.ejected_donor_ids)
    remaining = [d for d in all_active_donors if d.id not in ejected]
    scenario_state = _evaluate(
        bridge,
        active_donors=remaining,
        candidate_pool=candidate_pool,
        predictor=predictor,
        today=today,
        at_risk_threshold=at_risk_threshold,
        top_k_candidates=top_k_candidates,
    )

    delta = ScenarioDelta(
        cohort_size_change=scenario_state.active_donor_count - baseline.active_donor_count,
        avg_churn_change=scenario_state.avg_churn_90d - baseline.avg_churn_90d,
        at_risk_change=scenario_state.at_risk_count - baseline.at_risk_count,
        schedule_slots_change=scenario_state.schedule_slots_count
        - baseline.schedule_slots_count,
        schedule_objective_change=scenario_state.schedule_objective
        - baseline.schedule_objective,
    )

    return ScenarioOutcome(
        bridge_id=bridge.id,
        bridge_name=bridge.name,
        today=today,
        requested=scenario,
        baseline=baseline,
        scenario=scenario_state,
        delta=delta,
    )
