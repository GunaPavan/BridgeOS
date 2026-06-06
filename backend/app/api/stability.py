"""Stability API: ML-driven churn predictions for every donor in a bridge."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.ml.stability import StabilityPredictor, extract_features, get_predictor
from app.models import Bridge, BridgeMembership, BridgeHealth, MembershipStatus
from app.schemas import (
    BridgeStability,
    BridgeStabilityAggregate,
    DonorStability,
    StabilityFactor,
)

router = APIRouter(prefix="/bridges", tags=["stability"])

MODEL_VERSION = "stability_v1"


def get_predictor_dep() -> StabilityPredictor | None:
    """FastAPI dependency wrapper — overridable in tests."""
    return get_predictor()


def _ml_health_from_avg(
    avg_churn_90d: float, *, db: Session | None = None
) -> BridgeHealth:
    """Map aggregate 90-day churn risk to a health bucket.

    Thresholds come from ``app.ml.calibration`` which derives them from the
    CURRENT data distribution (p60 of avg_churn -> at_risk boundary, p86 ->
    critical boundary). Previously hardcoded against synthetic data, which
    breaks the moment real data is ingested.
    """
    from app.ml.calibration import CalibratedThresholds, get_thresholds

    thresholds: CalibratedThresholds
    if db is not None:
        thresholds = get_thresholds(db)
    else:
        thresholds = CalibratedThresholds.neutral()

    if avg_churn_90d >= thresholds.at_risk_cutoff:
        return BridgeHealth.CRITICAL
    if avg_churn_90d >= thresholds.stable_cutoff:
        return BridgeHealth.AT_RISK
    return BridgeHealth.STABLE


_HEALTH_SEVERITY = {
    BridgeHealth.STABLE: 0,
    BridgeHealth.AT_RISK: 1,
    BridgeHealth.CRITICAL: 2,
}


def _floor_by_headcount(
    active_donor_count: int,
    patient_cadence_days: int | None = None,
) -> BridgeHealth:
    """Headcount-only health floor — delegates to ``bridge_health_from_headcount``.

    A probabilistic churn score should NEVER be more optimistic than this
    physical-headcount floor: a 2-donor cohort cannot be 'stable' regardless
    of what the model thinks of those donors. The floor scales with the
    patient's transfusion cadence (more frequent transfusions need more
    rotating donors to stay within the 90-day deferral).
    """
    from app.models.bridge import bridge_health_from_headcount
    return bridge_health_from_headcount(active_donor_count, patient_cadence_days)


def _combined_ml_health(
    avg_churn_90d: float,
    active_donor_count: int,
    *,
    patient_cadence_days: int | None = None,
    db: Session | None = None,
) -> BridgeHealth:
    """ML health, but never more optimistic than the headcount floor."""
    ml = _ml_health_from_avg(avg_churn_90d, db=db)
    floor = _floor_by_headcount(active_donor_count, patient_cadence_days)
    return ml if _HEALTH_SEVERITY[ml] >= _HEALTH_SEVERITY[floor] else floor


@router.get(
    "/{bridge_id}/stability",
    response_model=BridgeStability,
    summary="Cohort stability prediction (XGBoost + SHAP)",
)
def get_bridge_stability(
    bridge_id: uuid.UUID,
    db: Session = Depends(get_db),
    predictor: StabilityPredictor | None = Depends(get_predictor_dep),
) -> BridgeStability:
    """Return per-donor churn probabilities (30/60/90d) + bridge-level aggregate.

    Returns 503 if the model has not been trained yet
    (run `python -m scripts.train_stability` to fix).
    """
    if predictor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Stability model is not loaded. Train it with "
                "`python -m scripts.train_stability` and restart the server."
            ),
        )

    stmt = (
        select(Bridge)
        .options(
            joinedload(Bridge.patient),
            joinedload(Bridge.memberships)
            .joinedload(BridgeMembership.donor),
        )
        .where(Bridge.id == bridge_id)
    )
    bridge = db.execute(stmt).unique().scalar_one_or_none()
    if bridge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bridge {bridge_id} not found",
        )

    active_memberships = [
        m for m in bridge.memberships if m.status == MembershipStatus.ACTIVE
    ]
    today = date.today()

    # G2: lazy no-reply decay for every active donor before we extract features.
    # An outbound older than 48h with no inbound bumps response_rate downward,
    # which the model picks up on this very request.
    from app.services.response_feedback import apply_no_reply_decay_for_bridge

    apply_no_reply_decay_for_bridge(db, [m.donor for m in active_memberships])
    db.flush()

    feature_vectors = [extract_features(m.donor, bridge, today) for m in active_memberships]
    predictions = predictor.predict_batch(feature_vectors)

    members = [
        DonorStability(
            donor_id=m.donor.id,
            donor_name=m.donor.name,
            churn_30d=pred.churn_30d,
            churn_60d=pred.churn_60d,
            churn_90d=pred.churn_90d,
            top_factors=[StabilityFactor(**asdict(f)) for f in pred.top_factors],
        )
        for m, pred in zip(active_memberships, predictions)
    ]

    if members:
        churns_90 = [m.churn_90d for m in members]
        avg = sum(churns_90) / len(churns_90)
        mx = max(churns_90)
        at_risk = sum(1 for c in churns_90 if c >= 0.5)
    else:
        avg, mx, at_risk = 0.0, 0.0, 0

    aggregate = BridgeStabilityAggregate(
        # Use _combined_ so the panel can never say "stable" on a 2-donor
        # cohort that the bridge header already badged "critical".
        # Pass db so thresholds calibrate to the live data distribution,
        # and pass cadence so the headcount floor scales with the patient's
        # actual transfusion demand.
        ml_health=_combined_ml_health(
            avg,
            len(members),
            patient_cadence_days=bridge.patient_cadence_days,
            db=db,
        ),
        avg_churn_90d=avg,
        max_churn_90d=mx,
        at_risk_donor_count=at_risk,
        active_donor_count=len(members),
    )

    return BridgeStability(
        bridge_id=bridge.id,
        bridge_name=bridge.name,
        computed_at=datetime.now(timezone.utc),
        model_version=MODEL_VERSION,
        aggregate=aggregate,
        members=sorted(members, key=lambda x: x.churn_90d, reverse=True),
    )
