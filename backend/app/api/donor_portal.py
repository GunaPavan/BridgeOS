"""E14.B — donor self-service portal.

All endpoints scoped to the currently logged-in donor (via Cognito
``custom:linked_id`` → Donor.id). Privacy filter: donor sees:

  - The patients they donate to (name, age, hospital, next slot, # active donors)
  - Their own donation history + cooldowns + outreach pings
  - Their own preferences

Donor does NOT see:
  - Other donors' identities (only counts)
  - Other patients
  - Operator/admin tooling
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.integrations.cognito_auth import (
    AuthenticatedUser,
    require_donor_with_link,
)
from app.models import (
    Bridge,
    BridgeMembership,
    ContactChannel,
    CooldownReason,
    Donor,
    Language,
    MembershipStatus,
    OutreachCooldown,
    OutreachPing,
    OutreachWave,
    Patient,
    PingResponse,
)

router = APIRouter(prefix="/donor/me", tags=["donor-portal"])


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------


class DonorMeOut(BaseModel):
    id: uuid.UUID
    name: str
    age: int
    blood_group: str
    phone: str
    email: Optional[str]
    city: str
    state: str
    preferred_language: str
    preferred_channel: str
    total_donations: int
    response_rate: float
    is_active: bool


class DonorBridgeOut(BaseModel):
    """A bridge the donor is assigned to. Patient identity shown; sibling
    donor names redacted to a count."""

    bridge_id: uuid.UUID
    patient_name: str
    patient_age: int
    patient_blood_group: str
    hospital: str
    city: str
    membership_status: str
    role: Optional[str]
    next_transfusion_date: Optional[str]
    other_active_donor_count: int


class CooldownOut(BaseModel):
    reason: str
    patient_id: Optional[uuid.UUID]
    patient_name: Optional[str]
    expires_at: datetime
    days_remaining: int
    notes: Optional[str]


class PingHistoryOut(BaseModel):
    ping_id: uuid.UUID
    wave_id: uuid.UUID
    patient_name: str
    sent_at: Optional[datetime]
    response: str
    response_at: Optional[datetime]
    template_key: Optional[str]
    language: Optional[str]


class PreferencesPatch(BaseModel):
    preferred_channel: Optional[ContactChannel] = None
    preferred_language: Optional[Language] = None

    @field_validator("preferred_channel", mode="before")
    @classmethod
    def _normalise_channel(cls, v):
        return v.lower() if isinstance(v, str) else v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_donor(db: Session, user: AuthenticatedUser) -> Donor:
    """Look up Donor by Cognito custom:linked_id, fall back to email."""
    if user.linked_id:
        try:
            d = db.get(Donor, uuid.UUID(user.linked_id))
            if d is not None:
                return d
        except ValueError:
            pass
    # Fallback: match by email (donor signed up before admin linked them)
    if user.email:
        d = (
            db.execute(select(Donor).where(Donor.email == user.email))
            .scalars()
            .first()
        )
        if d is not None:
            return d
    raise HTTPException(
        status_code=404,
        detail="No Donor record linked to your account. Ask your coordinator to link it.",
    )


def _enum_value(x) -> str:
    return getattr(x, "value", str(x)) if x is not None else ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=DonorMeOut,
    summary="Current donor profile",
)
def get_me(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_donor_with_link),
) -> DonorMeOut:
    d = _resolve_donor(db, user)
    return DonorMeOut(
        id=d.id, name=d.name, age=d.age,
        blood_group=_enum_value(d.blood_group),
        phone=d.phone, email=d.email,
        city=d.city, state=d.state,
        preferred_language=_enum_value(d.preferred_language),
        preferred_channel=_enum_value(d.preferred_channel),
        total_donations=d.total_donations or 0,
        response_rate=float(d.response_rate or 0),
        is_active=d.is_active,
    )


@router.get(
    "/bridges",
    response_model=list[DonorBridgeOut],
    summary="Bridges this donor serves (patient identity shown; sibling donors redacted to count)",
)
def get_my_bridges(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_donor_with_link),
) -> list[DonorBridgeOut]:
    d = _resolve_donor(db, user)
    rows = (
        db.execute(
            select(BridgeMembership).where(
                BridgeMembership.donor_id == d.id,
                BridgeMembership.status.in_([
                    MembershipStatus.ACTIVE.value,
                    MembershipStatus.PENDING.value,
                ]),
            )
        )
        .scalars()
        .all()
    )
    out: list[DonorBridgeOut] = []
    for m in rows:
        bridge = db.get(Bridge, m.bridge_id)
        if bridge is None or bridge.patient is None:
            continue
        patient = bridge.patient
        # Compute the donor's next slot (next transfusion + own status check)
        next_t = None
        if patient.last_transfusion_date and patient.transfusion_cadence_days:
            next_d = patient.last_transfusion_date + timedelta(
                days=patient.transfusion_cadence_days
            )
            next_t = next_d.isoformat()
        # Count other active donors WITHOUT exposing identities
        other_active = sum(
            1 for mm in bridge.memberships
            if mm.donor_id != d.id
            and getattr(mm.status, "value", str(mm.status)) == MembershipStatus.ACTIVE.value
        )
        out.append(DonorBridgeOut(
            bridge_id=bridge.id,
            patient_name=patient.name,
            patient_age=patient.age,
            patient_blood_group=_enum_value(patient.blood_group),
            hospital=patient.hospital,
            city=patient.city,
            membership_status=_enum_value(m.status),
            role=_enum_value(m.role) if m.role else None,
            next_transfusion_date=next_t,
            other_active_donor_count=other_active,
        ))
    return out


@router.get(
    "/cooldowns",
    response_model=list[CooldownOut],
    summary="Active cooldowns affecting this donor",
)
def get_my_cooldowns(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_donor_with_link),
) -> list[CooldownOut]:
    d = _resolve_donor(db, user)
    now = datetime.utcnow()
    rows = (
        db.execute(
            select(OutreachCooldown).where(
                OutreachCooldown.donor_id == d.id,
                OutreachCooldown.expires_at > now,
            )
        )
        .scalars()
        .all()
    )
    out: list[CooldownOut] = []
    for c in rows:
        pname = None
        if c.patient_id is not None:
            p = db.get(Patient, c.patient_id)
            pname = p.name if p else None
        days = max(0, (c.expires_at - now).days)
        out.append(CooldownOut(
            reason=_enum_value(c.reason),
            patient_id=c.patient_id,
            patient_name=pname,
            expires_at=c.expires_at,
            days_remaining=days,
            notes=c.notes,
        ))
    return out


@router.get(
    "/pings",
    response_model=list[PingHistoryOut],
    summary="Recent outreach pings this donor received",
)
def get_my_pings(
    limit: int = 50,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_donor_with_link),
) -> list[PingHistoryOut]:
    d = _resolve_donor(db, user)
    rows = (
        db.execute(
            select(OutreachPing)
            .where(OutreachPing.donor_id == d.id)
            .order_by(OutreachPing.sent_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    out: list[PingHistoryOut] = []
    for p in rows:
        wave = p.wave
        pname = "(unknown)"
        if wave and wave.patient_id:
            patient = db.get(Patient, wave.patient_id)
            if patient is not None:
                pname = patient.name
        out.append(PingHistoryOut(
            ping_id=p.id,
            wave_id=p.wave_id,
            patient_name=pname,
            sent_at=p.sent_at,
            response=_enum_value(p.response),
            response_at=p.response_at,
            template_key=p.template_key,
            language=p.language,
        ))
    return out


@router.patch(
    "/preferences",
    response_model=DonorMeOut,
    summary="Update preferred channel + language",
)
def patch_my_preferences(
    payload: PreferencesPatch = Body(...),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_donor_with_link),
) -> DonorMeOut:
    d = _resolve_donor(db, user)
    if payload.preferred_channel is not None:
        d.preferred_channel = payload.preferred_channel
    if payload.preferred_language is not None:
        d.preferred_language = payload.preferred_language
    db.commit()
    db.refresh(d)
    return DonorMeOut(
        id=d.id, name=d.name, age=d.age,
        blood_group=_enum_value(d.blood_group),
        phone=d.phone, email=d.email,
        city=d.city, state=d.state,
        preferred_language=_enum_value(d.preferred_language),
        preferred_channel=_enum_value(d.preferred_channel),
        total_donations=d.total_donations or 0,
        response_rate=float(d.response_rate or 0),
        is_active=d.is_active,
    )


@router.post(
    "/opt-out",
    summary="Stop all future outreach (cross-patient opt-out cooldown)",
)
def opt_out(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_donor_with_link),
) -> dict:
    d = _resolve_donor(db, user)
    # Apply a long-lived global cooldown via the same cooldown table
    now = datetime.utcnow()
    expires = now + timedelta(days=365)
    # Avoid duplicates by checking for an existing OPT_OUT_TEMPORARY row
    existing = (
        db.execute(
            select(OutreachCooldown).where(
                OutreachCooldown.donor_id == d.id,
                OutreachCooldown.reason == CooldownReason.OPT_OUT_TEMPORARY,
                OutreachCooldown.patient_id.is_(None),
                OutreachCooldown.expires_at > now,
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        db.add(OutreachCooldown(
            donor_id=d.id,
            patient_id=None,
            reason=CooldownReason.OPT_OUT_TEMPORARY,
            expires_at=expires,
            applied_at=now,
            notes="Donor opted out via self-service portal",
        ))
    d.is_active = False
    db.commit()
    return {"opted_out": True, "expires_at": expires.isoformat()}
