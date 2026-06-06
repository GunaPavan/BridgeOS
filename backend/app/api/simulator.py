"""Simulator API — stateless what-if endpoint."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.stability import get_predictor_dep
from app.db import get_db
from app.ml.stability import StabilityPredictor
from app.models import Bridge, BridgeMembership, Donor
from app.schemas.donor import DonorSummary
from app.schemas.recommendation import (
    CandidateOut,
    CandidateRationaleOut,
    StabilityFactor,
    WeakDonorOut,
)
from app.schemas.simulator import (
    CohortMemberStateOut,
    ScenarioDeltaOut,
    ScenarioOutcomeOut,
    ScenarioRequest,
    ScenarioStateOut,
)
from app.simulator import Scenario, ScenarioOutcome, compute_scenario

router = APIRouter(prefix="/simulator", tags=["simulator"])


def _load_bridge(db: Session, bridge_id: uuid.UUID) -> Bridge:
    stmt = (
        select(Bridge)
        .options(
            joinedload(Bridge.patient),
            joinedload(Bridge.memberships).joinedload(BridgeMembership.donor),
        )
        .where(Bridge.id == bridge_id)
    )
    bridge = db.execute(stmt).unique().scalar_one_or_none()
    if bridge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bridge {bridge_id} not found",
        )
    return bridge


def _serialize_state(state) -> ScenarioStateOut:
    return ScenarioStateOut(
        active_donor_count=state.active_donor_count,
        cohort=[
            CohortMemberStateOut(
                donor_id=c.donor_id,
                donor_name=c.donor_name,
                blood_group=c.blood_group,
                churn_30d=c.churn_30d,
                churn_60d=c.churn_60d,
                churn_90d=c.churn_90d,
            )
            for c in state.cohort
        ],
        avg_churn_90d=state.avg_churn_90d,
        max_churn_90d=state.max_churn_90d,
        at_risk_count=state.at_risk_count,
        schedule_status=state.schedule_status,
        schedule_slots_count=state.schedule_slots_count,
        schedule_objective=state.schedule_objective,
        schedule_solve_time_ms=state.schedule_solve_time_ms,
        weak_donors=[
            WeakDonorOut(
                membership_id=w.membership.id,
                donor_id=w.membership.donor_id,
                donor_name=w.membership.donor.name,
                role=w.membership.role.value
                if hasattr(w.membership.role, "value")
                else str(w.membership.role),
                churn_90d=w.churn_90d,
                top_factors=[StabilityFactor(**asdict(f)) for f in w.top_factors],
            )
            for w in state.weak_donors
        ],
        top_candidates=[
            CandidateOut(
                donor=DonorSummary.model_validate(c.donor),
                composite_score=c.composite_score,
                distance_km=c.distance_km,
                predicted_churn_90d=c.predicted_churn_90d,
                days_until_eligible=c.days_until_eligible,
                rationale=[CandidateRationaleOut(**asdict(r)) for r in c.rationale],
            )
            for c in state.top_candidates
        ],
    )


def _serialize_outcome(outcome: ScenarioOutcome) -> ScenarioOutcomeOut:
    return ScenarioOutcomeOut(
        bridge_id=outcome.bridge_id,
        bridge_name=outcome.bridge_name,
        today=outcome.today,
        requested=ScenarioRequest(
            ejected_donor_ids=list(outcome.requested.ejected_donor_ids)
        ),
        baseline=_serialize_state(outcome.baseline),
        scenario=_serialize_state(outcome.scenario),
        delta=ScenarioDeltaOut(
            cohort_size_change=outcome.delta.cohort_size_change,
            avg_churn_change=outcome.delta.avg_churn_change,
            at_risk_change=outcome.delta.at_risk_change,
            schedule_slots_change=outcome.delta.schedule_slots_change,
            schedule_objective_change=outcome.delta.schedule_objective_change,
        ),
    )


@router.post(
    "/bridges/{bridge_id}/scenario",
    response_model=ScenarioOutcomeOut,
    summary="What-if: eject donor(s) and recompute everything without writing to the DB",
)
def run_scenario(
    bridge_id: uuid.UUID,
    payload: ScenarioRequest = Body(default_factory=ScenarioRequest),
    db: Session = Depends(get_db),
    predictor: StabilityPredictor | None = Depends(get_predictor_dep),
) -> ScenarioOutcomeOut:
    if predictor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Stability model is not loaded. Run "
                "`python -m scripts.train_stability` and restart the server."
            ),
        )

    bridge = _load_bridge(db, bridge_id)
    donor_pool = list(
        db.execute(select(Donor).options(joinedload(Donor.memberships)))
        .unique()
        .scalars()
        .all()
    )
    outcome = compute_scenario(
        bridge=bridge,
        candidate_pool=donor_pool,
        predictor=predictor,
        today=date.today(),
        scenario=Scenario(ejected_donor_ids=list(payload.ejected_donor_ids)),
    )
    return _serialize_outcome(outcome)
