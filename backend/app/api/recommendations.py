"""Recommendations + recruitment API."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.services import whatsapp_templates as _tmpl
from app.api.stability import get_predictor_dep
from app.db import get_db
from app.integrations import twilio_client
from app.ml.stability import StabilityPredictor
from app.models import (
    Bridge,
    BridgeMembership,
    Donor,
    MembershipRole,
    MembershipStatus,
    MessageDirection,
    MessageStatus,
    WhatsAppMessage,
)
from app.recommender import (
    AT_RISK_CHURN_THRESHOLD,
    BridgeRecommendation,
    compute_recommendations_for_bridge,
    list_bridges_with_recommendations,
)
from app.recommender.engine import _can_donate_to
from app.schemas import (
    BridgeRecommendationOut,
    CandidateOut,
    CandidateRationaleOut,
    RecommendationsInbox,
    RecruitRequest,
    RecruitResponse,
    StabilityFactor,
    WeakDonorOut,
)
from app.schemas.donor import DonorSummary
from app.schemas.recommendation import PendingRecruitOut


router = APIRouter(tags=["recommendations"])


def _require_predictor(predictor: StabilityPredictor | None) -> StabilityPredictor:
    if predictor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Stability model is not loaded. Run "
                "`python -m scripts.train_stability` and restart the server."
            ),
        )
    return predictor


def _to_out(rec: BridgeRecommendation) -> BridgeRecommendationOut:
    bridge = rec.bridge
    patient = bridge.patient
    return BridgeRecommendationOut(
        bridge_id=bridge.id,
        bridge_name=bridge.name,
        patient_id=patient.id,
        patient_name=patient.name,
        patient_age=patient.age,
        patient_blood_group=patient.blood_group,
        patient_hospital=patient.hospital,
        patient_city=patient.city,
        bridge_health_stub=bridge.health,
        active_donor_count=bridge.active_donor_count,
        urgency=rec.urgency,  # type: ignore[arg-type]
        weak_donors=[
            WeakDonorOut(
                membership_id=w.membership.id,
                donor_id=w.membership.donor_id,
                donor_name=w.membership.donor.name,
                role=w.membership.role.value if hasattr(w.membership.role, "value") else str(w.membership.role),
                churn_90d=w.churn_90d,
                top_factors=[StabilityFactor(**asdict(f)) for f in w.top_factors],
            )
            for w in rec.weak_donors
        ],
        candidates=[
            CandidateOut(
                donor=DonorSummary.model_validate(c.donor),
                composite_score=c.composite_score,
                distance_km=c.distance_km,
                predicted_churn_90d=c.predicted_churn_90d,
                days_until_eligible=c.days_until_eligible,
                rationale=[CandidateRationaleOut(**asdict(r)) for r in c.rationale],
            )
            for c in rec.candidates
        ],
    )


# ----- /recommendations inbox -----


@router.get(
    "/recommendations",
    response_model=RecommendationsInbox,
    summary="Cross-bridge inbox of recruitment recommendations",
)
def list_recommendations(
    only_weak: bool = Query(True, description="Only show bridges with at-risk donors"),
    top_k_per_bridge: int = Query(5, ge=1, le=20),
    at_risk_threshold: float = Query(
        AT_RISK_CHURN_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="90-day churn probability above which a donor is flagged as weak",
    ),
    db: Session = Depends(get_db),
    predictor: StabilityPredictor | None = Depends(get_predictor_dep),
) -> RecommendationsInbox:
    p = _require_predictor(predictor)
    recs = list_bridges_with_recommendations(
        db=db,
        predictor=p,
        today=date.today(),
        only_weak=only_weak,
        top_k_per_bridge=top_k_per_bridge,
        at_risk_threshold=at_risk_threshold,
    )
    items = [_to_out(r) for r in recs]
    return RecommendationsInbox(items=items, total=len(items))


# ----- per-bridge recommendations -----


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


@router.get(
    "/bridges/{bridge_id}/recommendations",
    response_model=BridgeRecommendationOut,
    summary="Recruitment recommendations for one bridge",
)
def get_bridge_recommendations(
    bridge_id: uuid.UUID,
    top_k: int = Query(5, ge=1, le=20),
    at_risk_threshold: float = Query(
        AT_RISK_CHURN_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="90-day churn probability above which a donor is flagged as weak",
    ),
    db: Session = Depends(get_db),
    predictor: StabilityPredictor | None = Depends(get_predictor_dep),
) -> BridgeRecommendationOut:
    p = _require_predictor(predictor)
    bridge = _load_bridge(db, bridge_id)

    donor_pool = list(
        db.execute(select(Donor).options(joinedload(Donor.memberships)))
        .unique()
        .scalars()
        .all()
    )
    rec = compute_recommendations_for_bridge(
        bridge=bridge,
        candidate_pool=donor_pool,
        predictor=p,
        today=date.today(),
        top_k=top_k,
        at_risk_threshold=at_risk_threshold,
    )
    return _to_out(rec)


# ----- recruit (POST /bridges/{id}/recruit) -----


@router.post(
    "/bridges/{bridge_id}/recruit",
    response_model=RecruitResponse,
    summary="Invite a candidate donor (PENDING until they reply YES on WhatsApp)",
)
def recruit_donor(
    bridge_id: uuid.UUID,
    payload: RecruitRequest = Body(...),
    db: Session = Depends(get_db),
) -> RecruitResponse:
    """G1: invite-with-consent.

    Inserts a PENDING BridgeMembership and fires a `recruit_invite` WhatsApp
    in the donor's language. The membership only flips to ACTIVE (and the
    replaced donor only flips to EXITED) when the donor's reply hits the
    webhook and `intent.classify()` returns ACCEPT.
    """
    bridge = _load_bridge(db, bridge_id)
    patient = bridge.patient

    candidate = db.get(Donor, payload.candidate_donor_id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate donor {payload.candidate_donor_id} not found",
        )

    if not _can_donate_to(candidate.blood_group, patient.blood_group):
        donor_bg = getattr(candidate.blood_group, "value", str(candidate.blood_group))
        patient_bg = getattr(patient.blood_group, "value", str(patient.blood_group))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Donor {candidate.name} ({donor_bg}) is not "
                f"ABO/Rh compatible with patient {patient.name} ({patient_bg})"
            ),
        )

    # Reject if the donor is already ACTIVE or PENDING in this bridge
    for m in bridge.memberships:
        if m.donor_id != candidate.id:
            continue
        status_val = getattr(m.status, "value", str(m.status))
        if status_val == MembershipStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Donor {candidate.name} is already active in this bridge",
            )
        if status_val == MembershipStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Donor {candidate.name} already has a PENDING invite for this "
                    f"bridge (membership {m.id}). Cancel or wait for their reply."
                ),
            )

    # Validate replace_donor_id (we DO NOT EXIT them yet — only on YES)
    replace_donor_id: Optional[uuid.UUID] = None
    if payload.replace_donor_id is not None:
        target = next(
            (
                m
                for m in bridge.memberships
                if m.donor_id == payload.replace_donor_id
                and getattr(m.status, "value", str(m.status))
                == MembershipStatus.ACTIVE.value
            ),
            None,
        )
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="replace_donor_id not found as an active member of this bridge",
            )
        replace_donor_id = payload.replace_donor_id

    # --- Insert PENDING membership ---
    pending = BridgeMembership(
        bridge_id=bridge.id,
        donor_id=candidate.id,
        role=MembershipRole.PRIMARY,
        status=MembershipStatus.PENDING,
        joined_at=date.today(),
        notes=payload.notes,
        replaces_donor_id=replace_donor_id,
    )
    db.add(pending)
    db.flush()  # give it an id before we set FK references on the message row

    # --- Fire WhatsApp recruit_invite (G4: via the unified template store) ---
    chosen_lang = (
        payload.language
        or getattr(candidate.preferred_language, "value", str(candidate.preferred_language))
        or "en"
    )
    donor_first = candidate.name.split()[0] if candidate.name else "there"
    patient_bg = getattr(patient.blood_group, "value", str(patient.blood_group))
    rendered = _tmpl.render(
        "recruit_invite",
        language=chosen_lang,
        donor_first=donor_first,
        donor_name=candidate.name,
        patient_name=patient.name,
        patient_age=patient.age,
        patient_blood_group=patient_bg,
    )
    body = rendered.body
    # If the requested language wasn't available, record the actual one we used.
    chosen_lang = rendered.language_used

    send_result = twilio_client.send_whatsapp(
        to_number=candidate.phone, body=body
    )

    pending.invite_message_sid = send_result.sid
    pending.invite_language = chosen_lang

    outbound = WhatsAppMessage(
        donor_id=candidate.id,
        bridge_id=bridge.id,
        direction=MessageDirection.OUTBOUND,
        from_number=twilio_client.whatsapp_from(),
        to_number=candidate.phone,
        body=body,
        status=(
            MessageStatus(send_result.status)
            if send_result.status in {s.value for s in MessageStatus}
            else MessageStatus.QUEUED
        ),
        twilio_sid=send_result.sid,
        template_key="recruit_invite",
        language=chosen_lang,
    )
    db.add(outbound)
    db.commit()
    db.refresh(pending)
    db.refresh(bridge)

    new_active = sum(
        1
        for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == MembershipStatus.ACTIVE.value
    )

    msg = (
        f"Invite sent to {candidate.name} ({chosen_lang}). "
        f"Membership pending donor reply"
        + (f" — will replace {payload.replace_donor_id}." if replace_donor_id else ".")
    )
    return RecruitResponse(
        bridge_id=bridge.id,
        added_membership_id=pending.id,
        added_donor_id=candidate.id,
        added_donor_name=candidate.name,
        status="pending",
        waiting_for_donor_reply=True,
        message_sid=send_result.sid,
        message_language=chosen_lang,  # type: ignore[arg-type]
        replace_donor_id=replace_donor_id,
        new_active_donor_count=new_active,
        message=msg,
    )


# ----- pending-recruits (GET /bridges/{id}/pending-recruits) -----


@router.get(
    "/bridges/{bridge_id}/pending-recruits",
    response_model=list[PendingRecruitOut],
    summary="List PENDING memberships on this bridge awaiting donor reply",
)
def list_pending_recruits(
    bridge_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[PendingRecruitOut]:
    bridge = _load_bridge(db, bridge_id)

    out: list[PendingRecruitOut] = []
    donor_name_by_id: dict[uuid.UUID, str] = {}
    for m in bridge.memberships:
        if getattr(m.status, "value", str(m.status)) != MembershipStatus.PENDING.value:
            continue
        candidate = db.get(Donor, m.donor_id)
        if candidate is None:
            continue
        replaces_name: Optional[str] = None
        if m.replaces_donor_id is not None:
            if m.replaces_donor_id not in donor_name_by_id:
                r = db.get(Donor, m.replaces_donor_id)
                donor_name_by_id[m.replaces_donor_id] = r.name if r else "?"
            replaces_name = donor_name_by_id[m.replaces_donor_id]
        out.append(
            PendingRecruitOut(
                membership_id=m.id,
                bridge_id=bridge.id,
                candidate_donor_id=candidate.id,
                candidate_donor_name=candidate.name,
                candidate_donor_phone=candidate.phone,
                candidate_donor_language=getattr(
                    candidate.preferred_language, "value", str(candidate.preferred_language)
                ),
                replaces_donor_id=m.replaces_donor_id,
                replaces_donor_name=replaces_name,
                invite_message_sid=m.invite_message_sid,
                invite_language=m.invite_language,
                joined_at=m.joined_at,
            )
        )
    return out
