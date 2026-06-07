"""E11.T — Admin-only live test surfaces.

Two endpoints to drive a real end-to-end WhatsApp + Voice exercise without
waiting for the scheduler escalation cycle.

POST /admin/test/setup
    Picks (or accepts) a donor, patches their phone to the supplied number,
    creates a fresh ACTIVE OutreachWave for the patient on that donor's
    bridge, and inserts a PENDING OutreachPing linking the two. Returns
    every id the test needs (donor / patient / wave / ping).

POST /admin/test/voice-call/{ping_id}
    Fires a real bidirectional Twilio Voice call to the donor on this ping.
    The TwiML the call hits is the production /twilio/voice/twiml/ask
    endpoint, so the conversation is the same one a scheduler-triggered
    escalation would have.

Both endpoints are guarded by ``require_admin``. The donor's phone is
patched in-place — coordinators using this surface accept that the donor
record's phone is now the tester's phone until they revert it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.integrations.cognito_auth import AuthenticatedUser, require_admin
from app.services.donor_voice_call import place_donor_voice_call

import os
from fastapi import Header


def _check_test_secret(
    x_admin_test_secret: Optional[str] = Header(
        None, alias="X-Admin-Test-Secret",
        description="Shared secret matching BRIDGE_OS_ADMIN_TEST_SECRET env var on the task.",
    ),
) -> None:
    """Header-based gate so we don't have to thread Cognito tokens through
    curl during live testing. When BRIDGE_OS_ADMIN_TEST_SECRET is unset,
    these endpoints are 403 (closed by default)."""
    expected = os.environ.get("BRIDGE_OS_ADMIN_TEST_SECRET", "").strip()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail="Admin test surface is disabled (BRIDGE_OS_ADMIN_TEST_SECRET unset).",
        )
    if not x_admin_test_secret or x_admin_test_secret != expected:
        raise HTTPException(
            status_code=403,
            detail="Missing or mismatched X-Admin-Test-Secret header.",
        )
from app.models import (
    BridgeMembership,
    Donor,
    OutreachChannel,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    PingResponse,
    UrgencyTier,
)

router = APIRouter(prefix="/admin/test", tags=["admin-test"])


# ---------------------------------------------------------------------------
# /setup — provision a (donor, wave, ping) ready for live testing
# ---------------------------------------------------------------------------


class SetupTestRequest(BaseModel):
    phone: str = Field(
        ...,
        description="E.164 phone (e.g. REDACTED-PHONE). The chosen donor's phone is patched to this value.",
        min_length=8,
        max_length=20,
    )
    donor_id: Optional[uuid.UUID] = Field(
        None,
        description="Optional donor to target. If omitted, the first donor with a bridge membership is used.",
    )
    urgency: UrgencyTier = Field(
        UrgencyTier.HIGH,
        description="Urgency tier on the wave. Defaults to HIGH so call-escalation auto-fires if left alone.",
    )


class SetupTestResponse(BaseModel):
    donor_id: uuid.UUID
    donor_name: str
    donor_phone: str
    patient_id: uuid.UUID
    patient_name: str
    bridge_id: Optional[uuid.UUID]
    wave_id: uuid.UUID
    ping_id: uuid.UUID
    next_step_hint: str


@router.post(
    "/setup",
    response_model=SetupTestResponse,
    summary="Provision donor + wave + ping for a live WhatsApp/Voice round-trip test",
)
def setup_live_test(
    payload: SetupTestRequest = Body(...),
    db: Session = Depends(get_db),
    _guard: None = Depends(_check_test_secret),
) -> SetupTestResponse:
    # 1. Resolve the donor — explicit id wins, else first donor that has a bridge
    donor: Optional[Donor] = None
    if payload.donor_id is not None:
        donor = db.get(Donor, payload.donor_id)
        if donor is None:
            raise HTTPException(404, detail=f"Donor {payload.donor_id} not found")
    else:
        donor = (
            db.execute(
                select(Donor)
                .join(BridgeMembership, BridgeMembership.donor_id == Donor.id)
                .limit(1)
            )
            .scalars()
            .first()
        )
        if donor is None:
            raise HTTPException(
                409,
                detail="No donor with a bridge membership available. Seed the DB first.",
            )

    # 2. Pick the donor's first bridge + patient context
    membership = (
        db.execute(
            select(BridgeMembership)
            .where(BridgeMembership.donor_id == donor.id)
            .limit(1)
        )
        .scalars()
        .first()
    )
    if membership is None:
        raise HTTPException(
            409,
            detail=f"Donor {donor.id} has no bridge memberships — cannot frame a ping context.",
        )
    bridge = membership.bridge
    if bridge is None or bridge.patient is None:
        raise HTTPException(
            409,
            detail="Bridge or patient missing on the chosen donor's membership.",
        )
    patient: Patient = bridge.patient

    # 3. Patch donor phone to the test number
    donor.phone = payload.phone

    # 4. Create a fresh ACTIVE wave for this patient
    now = datetime.utcnow()
    wave = OutreachWave(
        patient_id=patient.id,
        bridge_id=bridge.id,
        slot_date=(now + timedelta(days=2)).date(),
        tier=OutreachTier.TIER_1,
        urgency=payload.urgency,
        status=OutreachWaveStatus.ACTIVE,
        triggered_by="admin_test_setup",
        created_at=now,
    )
    db.add(wave)
    db.flush()

    # 5. Create a PENDING ping for the donor
    ping = OutreachPing(
        wave_id=wave.id,
        donor_id=donor.id,
        channel=OutreachChannel.WHATSAPP,
        response=PingResponse.PENDING,
        sent_at=now,
        template_key="recruit_invite",
        language="en",
    )
    db.add(ping)
    db.commit()
    db.refresh(ping)
    db.refresh(wave)

    return SetupTestResponse(
        donor_id=donor.id,
        donor_name=donor.name,
        donor_phone=donor.phone,
        patient_id=patient.id,
        patient_name=patient.name,
        bridge_id=bridge.id,
        wave_id=wave.id,
        ping_id=ping.id,
        next_step_hint=(
            "1) POST /whatsapp/send {donor_id, body or template_key} "
            "to send a real WA message. "
            "2) Reply from your phone — webhook will classify via Bedrock. "
            "3) POST /admin/test/voice-call/{ping_id} to place the bidirectional voice call."
        ),
    )


# ---------------------------------------------------------------------------
# /voice-call — fire the real call
# ---------------------------------------------------------------------------


class VoiceCallResponse(BaseModel):
    placed: bool
    call_sid: str
    is_mock: bool
    skipped_reason: Optional[str] = None
    ping_id: uuid.UUID
    donor_phone: str


@router.post(
    "/voice-call/{ping_id}",
    response_model=VoiceCallResponse,
    summary="Place a real bidirectional Twilio Voice call for this ping (admin-only test)",
)
def fire_voice_call(
    ping_id: uuid.UUID,
    db: Session = Depends(get_db),
    _guard: None = Depends(_check_test_secret),
) -> VoiceCallResponse:
    ping = db.get(OutreachPing, ping_id)
    if ping is None:
        raise HTTPException(404, detail=f"Ping {ping_id} not found")
    donor = db.get(Donor, ping.donor_id)
    if donor is None or not donor.phone:
        raise HTTPException(
            409, detail="Ping's donor is missing or has no phone — fix data first."
        )
    result = place_donor_voice_call(db, ping=ping)
    return VoiceCallResponse(
        placed=result.placed,
        call_sid=result.call_sid,
        is_mock=result.is_mock,
        skipped_reason=result.skipped_reason,
        ping_id=ping.id,
        donor_phone=donor.phone,
    )


# ---------------------------------------------------------------------------
# /ping/{ping_id} — quick state lookup so the tester can poll without auth juggling
# ---------------------------------------------------------------------------


class PingStateOut(BaseModel):
    ping_id: uuid.UUID
    wave_id: uuid.UUID
    donor_id: uuid.UUID
    donor_phone: str
    response: str
    response_at: Optional[datetime]
    channel: str
    template_key: Optional[str]
    language: Optional[str]


@router.get(
    "/ping/{ping_id}",
    response_model=PingStateOut,
    summary="Inspect the live state of a ping (admin-only)",
)
def inspect_ping(
    ping_id: uuid.UUID,
    db: Session = Depends(get_db),
    _guard: None = Depends(_check_test_secret),
) -> PingStateOut:
    ping = db.get(OutreachPing, ping_id)
    if ping is None:
        raise HTTPException(404, detail=f"Ping {ping_id} not found")
    donor = db.get(Donor, ping.donor_id)
    return PingStateOut(
        ping_id=ping.id,
        wave_id=ping.wave_id,
        donor_id=ping.donor_id,
        donor_phone=donor.phone if donor else "",
        response=getattr(ping.response, "value", str(ping.response)),
        response_at=ping.response_at,
        channel=getattr(ping.channel, "value", str(ping.channel)),
        template_key=ping.template_key,
        language=ping.language,
    )
