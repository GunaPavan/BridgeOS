"""E14.C — patient / caregiver self-service portal.

All endpoints scoped to the currently logged-in caregiver (via Cognito
``custom:linked_id`` → Patient.id, fallback Patient.caregiver_email).

The patient/caregiver sees:
  - Their bridge with FULL donor names (need to thank donors / know who's coming)
  - Their next transfusion date
  - Active outreach waves + status
  - Their caregiver preferences

They CANNOT see:
  - Other patients
  - Coordinator tooling
  - Donor personal info beyond name + city + blood group
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.integrations.cognito_auth import (
    AuthenticatedUser,
    require_patient_with_link,
)
from app.models import (
    Bridge,
    BridgeMembership,
    ContactChannel,
    Donor,
    Language,
    MembershipStatus,
    OutreachPing,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    PingResponse,
)

router = APIRouter(prefix="/patient/me", tags=["patient-portal"])


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------


class PatientMeOut(BaseModel):
    id: uuid.UUID
    name: str
    age: int
    blood_group: str
    city: str
    hospital: str
    transfusion_cadence_days: int
    last_transfusion_date: Optional[str]
    next_transfusion_date: Optional[str]
    caregiver_name: Optional[str]
    caregiver_email: Optional[str]
    caregiver_phone: Optional[str]
    caregiver_relation: Optional[str]
    caregiver_preferred_channel: str
    preferred_language: str


class DonorOnBridgeOut(BaseModel):
    donor_id: uuid.UUID
    name: str
    city: str
    blood_group: str
    last_donation_date: Optional[str]
    membership_status: str


class MyBridgeOut(BaseModel):
    bridge_id: uuid.UUID
    bridge_status: str
    active_donors: list[DonorOnBridgeOut]
    pending_donors: list[DonorOnBridgeOut]


class WaveSummaryOut(BaseModel):
    wave_id: uuid.UUID
    slot_date: str
    status: str
    urgency: str
    tier: str
    pings_sent: int
    pings_accepted: int
    pings_declined: int
    pings_no_reply: int
    created_at: datetime


class CaregiverPatch(BaseModel):
    caregiver_email: Optional[EmailStr] = None
    caregiver_preferred_channel: Optional[ContactChannel] = None
    preferred_language: Optional[Language] = None

    @field_validator("caregiver_preferred_channel", mode="before")
    @classmethod
    def _normalise_channel(cls, v):
        return v.lower() if isinstance(v, str) else v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_patient(db: Session, user: AuthenticatedUser) -> Patient:
    """Cognito custom:linked_id → Patient.id, fallback caregiver_email."""
    if user.linked_id:
        try:
            p = db.get(Patient, uuid.UUID(user.linked_id))
            if p is not None:
                return p
        except ValueError:
            pass
    if user.email:
        p = (
            db.execute(select(Patient).where(Patient.caregiver_email == user.email))
            .scalars()
            .first()
        )
        if p is not None:
            return p
    raise HTTPException(
        status_code=404,
        detail="No Patient record linked to your account. Ask your coordinator to link it.",
    )


def _enum_value(x) -> str:
    return getattr(x, "value", str(x)) if x is not None else ""


def _next_transfusion(patient: Patient) -> Optional[str]:
    if patient.last_transfusion_date and patient.transfusion_cadence_days:
        from datetime import timedelta as _td
        return (
            patient.last_transfusion_date + _td(days=patient.transfusion_cadence_days)
        ).isoformat()
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PatientMeOut,
    summary="Current patient profile (caregiver view)",
)
def get_me(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_patient_with_link),
) -> PatientMeOut:
    p = _resolve_patient(db, user)
    return PatientMeOut(
        id=p.id, name=p.name, age=p.age,
        blood_group=_enum_value(p.blood_group),
        city=p.city, hospital=p.hospital,
        transfusion_cadence_days=p.transfusion_cadence_days,
        last_transfusion_date=p.last_transfusion_date.isoformat() if p.last_transfusion_date else None,
        next_transfusion_date=_next_transfusion(p),
        caregiver_name=p.caregiver_name,
        caregiver_email=p.caregiver_email,
        caregiver_phone=p.caregiver_phone,
        caregiver_relation=_enum_value(p.caregiver_relation) if p.caregiver_relation else None,
        caregiver_preferred_channel=_enum_value(p.caregiver_preferred_channel),
        preferred_language=_enum_value(p.preferred_language),
    )


@router.get(
    "/bridge",
    response_model=MyBridgeOut,
    summary="The bridge for this patient — with donor names visible",
)
def get_my_bridge(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_patient_with_link),
) -> MyBridgeOut:
    p = _resolve_patient(db, user)
    if p.bridge is None:
        raise HTTPException(404, detail="No bridge yet — coordinator will create one.")
    bridge = p.bridge
    active: list[DonorOnBridgeOut] = []
    pending: list[DonorOnBridgeOut] = []
    for m in bridge.memberships:
        donor = db.get(Donor, m.donor_id)
        if donor is None:
            continue
        status = _enum_value(m.status)
        row = DonorOnBridgeOut(
            donor_id=donor.id,
            name=donor.name,
            city=donor.city,
            blood_group=_enum_value(donor.blood_group),
            last_donation_date=donor.last_donation_date.isoformat() if donor.last_donation_date else None,
            membership_status=status,
        )
        if status == MembershipStatus.ACTIVE.value:
            active.append(row)
        elif status == MembershipStatus.PENDING.value:
            pending.append(row)
    return MyBridgeOut(
        bridge_id=bridge.id,
        bridge_status=_enum_value(bridge.status),
        active_donors=active,
        pending_donors=pending,
    )


@router.get(
    "/outreach",
    response_model=list[WaveSummaryOut],
    summary="Active outreach waves for this patient",
)
def get_my_outreach(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_patient_with_link),
) -> list[WaveSummaryOut]:
    p = _resolve_patient(db, user)
    rows = (
        db.execute(
            select(OutreachWave)
            .where(OutreachWave.patient_id == p.id)
            .order_by(OutreachWave.created_at.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )
    out: list[WaveSummaryOut] = []
    for w in rows:
        sent = sum(1 for ping in w.pings if ping.sent_at is not None)
        acc = sum(1 for ping in w.pings if ping.response == PingResponse.ACCEPTED)
        dec = sum(1 for ping in w.pings if ping.response == PingResponse.DECLINED)
        nr  = sum(1 for ping in w.pings if ping.response == PingResponse.NO_REPLY)
        out.append(WaveSummaryOut(
            wave_id=w.id,
            slot_date=w.slot_date.isoformat(),
            status=_enum_value(w.status),
            urgency=_enum_value(w.urgency),
            tier=_enum_value(w.tier),
            pings_sent=sent,
            pings_accepted=acc,
            pings_declined=dec,
            pings_no_reply=nr,
            created_at=w.created_at,
        ))
    return out


@router.patch(
    "/caregiver",
    response_model=PatientMeOut,
    summary="Update caregiver preferences (channel + language + email)",
)
def patch_my_caregiver(
    payload: CaregiverPatch = Body(...),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_patient_with_link),
) -> PatientMeOut:
    p = _resolve_patient(db, user)
    if payload.caregiver_email is not None:
        p.caregiver_email = str(payload.caregiver_email)
    if payload.caregiver_preferred_channel is not None:
        p.caregiver_preferred_channel = payload.caregiver_preferred_channel
    if payload.preferred_language is not None:
        p.preferred_language = payload.preferred_language
    db.commit()
    db.refresh(p)
    return get_me(db, user)  # reuse formatting


@router.post(
    "/outreach/cancel",
    summary="Cancel all active outreach (we found a donor ourselves)",
)
def cancel_outreach(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_patient_with_link),
) -> dict:
    p = _resolve_patient(db, user)
    now = datetime.utcnow()
    cancelled_waves = 0
    cancelled_pings = 0
    waves = (
        db.execute(
            select(OutreachWave).where(
                OutreachWave.patient_id == p.id,
                OutreachWave.status == OutreachWaveStatus.ACTIVE,
            )
        )
        .scalars()
        .all()
    )
    for w in waves:
        w.status = OutreachWaveStatus.EXPIRED
        cancelled_waves += 1
        for ping in w.pings:
            if ping.response == PingResponse.PENDING:
                ping.response = PingResponse.CANCELLED
                ping.response_at = now
                cancelled_pings += 1
    db.commit()
    return {
        "cancelled_waves": cancelled_waves,
        "cancelled_pings": cancelled_pings,
    }
