"""One-click demo fan-out across all four outbound channels.

POST /admin/demo/fire-all
    Provisions a demo donor + ping bound to the hardcoded demo contacts,
    then fires Voice (Twilio), WhatsApp (Twilio), SMS (AWS SNS), and Email
    (AWS SES) concurrently. Returns per-channel SID / message-id / status
    so the UI can render four live "✓ sent" tiles.

This endpoint exists so a judge can hit ONE button on the /system/scheduler
page and see all four channels light up on the presenter's phone within
~3 seconds. The voice call is the same full patient-context conversation
the production allocator would place — Twilio trial intro + Polly Kajal
question about Ganesh's B+ donation + speech Gather + Bedrock-classified
confirmation.

Contacts default to the values used during pre-deploy verification, but
can be overridden per-environment via BRIDGE_OS_DEMO_PHONE and
BRIDGE_OS_DEMO_EMAIL — e.g. another presenter shouldn't have to edit code
to point the demo at their own number.

Gated by the same ``BRIDGE_OS_ADMIN_TEST_SECRET`` header as /admin/test/*
so an unauthenticated visitor can't spam the presenter's phone.
"""

from __future__ import annotations

import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin_test import _check_test_secret
from app.db import SessionLocal, get_db
from app.integrations import sns_sms_client, ses_client, twilio_client
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
from app.services.demo_outreach import (
    OutreachBundle,
    cache_voice_question,
    compose_outreach,
)
from app.services.donor_voice_call import place_donor_voice_call

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/demo", tags=["admin-demo"])


# ---------------------------------------------------------------------------
# Defaults — overridable per-env so other presenters can run the same demo
# ---------------------------------------------------------------------------

_DEFAULT_DEMO_PHONE = "REDACTED-PHONE"
_DEFAULT_DEMO_EMAIL = "gunapavan4321@gmail.com"


def _demo_phone() -> str:
    return os.environ.get("BRIDGE_OS_DEMO_PHONE", _DEFAULT_DEMO_PHONE).strip() or _DEFAULT_DEMO_PHONE


def _demo_email() -> str:
    return os.environ.get("BRIDGE_OS_DEMO_EMAIL", _DEFAULT_DEMO_EMAIL).strip() or _DEFAULT_DEMO_EMAIL


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


class ChannelResult(BaseModel):
    channel: str = Field(..., description="voice | whatsapp | sms | email")
    ok: bool
    is_mock: bool
    sid_or_message_id: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0


class DemoContext(BaseModel):
    phone: str
    email: str
    donor_id: uuid.UUID
    donor_name: str
    patient_id: uuid.UUID
    patient_name: str
    ping_id: uuid.UUID


class OutreachCopy(BaseModel):
    """The Bedrock-generated (or fallback) copy used across all 4 channels.

    Shown in the UI so judges see the LLM-composed text + which model wrote
    it. ``source`` is "bedrock" / "anthropic" / "mock" / "template_fallback".
    """

    source: str
    model: str
    voice_question: str
    whatsapp_body: str
    sms_body: str
    email_subject: str
    email_body: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None


class FireAllResponse(BaseModel):
    fired_at: datetime
    total_duration_ms: int
    context: DemoContext
    copy: OutreachCopy
    channels: list[ChannelResult]


# ---------------------------------------------------------------------------
# Internal — provision (or refresh) a demo donor + ping
# ---------------------------------------------------------------------------


def _provision_demo_ping(db: Session, *, phone: str) -> tuple[Donor, Patient, OutreachPing]:
    """Returns a (donor, patient, ping) triple ready to drive the voice call.

    Re-uses the first donor with a bridge membership — same selection rule
    as ``/admin/test/setup`` — and patches its phone to the demo number so
    the call/WA/SMS actually reach the presenter's device. Always creates a
    fresh ACTIVE wave + PENDING ping so the voice-call handler has clean
    state to read patient context from.
    """
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
            status_code=409,
            detail="No donor with a bridge membership available. Seed the DB first.",
        )

    membership = (
        db.execute(
            select(BridgeMembership).where(BridgeMembership.donor_id == donor.id).limit(1)
        )
        .scalars()
        .first()
    )
    if membership is None or membership.bridge is None or membership.bridge.patient is None:
        raise HTTPException(
            status_code=409,
            detail="Chosen donor has no bridge/patient — can't build a voice question.",
        )
    patient: Patient = membership.bridge.patient

    # Patch donor phone to the demo target so all channels reach the presenter.
    donor.phone = phone

    now = datetime.utcnow()
    wave = OutreachWave(
        patient_id=patient.id,
        bridge_id=membership.bridge.id,
        slot_date=(now + timedelta(days=2)).date(),
        tier=OutreachTier.TIER_1,
        urgency=UrgencyTier.HIGH,
        status=OutreachWaveStatus.ACTIVE,
        triggered_by="admin_demo_fire_all",
        created_at=now,
    )
    db.add(wave)
    db.flush()

    ping = OutreachPing(
        wave_id=wave.id,
        donor_id=donor.id,
        channel=OutreachChannel.WHATSAPP,
        response=PingResponse.PENDING,
        sent_at=now,
        template_key="demo_fire_all",
        language="en",
    )
    db.add(ping)
    db.commit()
    db.refresh(ping)
    db.refresh(donor)
    return donor, patient, ping


# ---------------------------------------------------------------------------
# Per-channel firers — each opens its own session so they're thread-safe
# ---------------------------------------------------------------------------


def _ms_since(start: datetime) -> int:
    return int((datetime.utcnow() - start).total_seconds() * 1000)


def _fire_voice(ping_id: uuid.UUID) -> ChannelResult:
    start = datetime.utcnow()
    try:
        with SessionLocal() as db:
            ping = db.get(OutreachPing, ping_id)
            if ping is None:
                return ChannelResult(
                    channel="voice", ok=False, is_mock=True,
                    error=f"ping {ping_id} vanished mid-demo", duration_ms=_ms_since(start),
                )
            result = place_donor_voice_call(db, ping=ping)
        return ChannelResult(
            channel="voice",
            ok=result.placed,
            is_mock=result.is_mock,
            sid_or_message_id=result.call_sid or None,
            status="queued" if result.placed else (result.skipped_reason or "failed"),
            error=result.skipped_reason if not result.placed else None,
            duration_ms=_ms_since(start),
        )
    except Exception as exc:  # pragma: no cover — last-resort safety
        logger.exception("voice channel failed in demo fan-out")
        return ChannelResult(
            channel="voice", ok=False, is_mock=False,
            error=str(exc)[:300], duration_ms=_ms_since(start),
        )


def _fire_whatsapp(phone: str, body: str) -> ChannelResult:
    start = datetime.utcnow()
    try:
        result = twilio_client.send_whatsapp(to_number=phone, body=body)
        return ChannelResult(
            channel="whatsapp",
            ok=result.status not in ("failed", "undelivered"),
            is_mock=result.is_mock,
            sid_or_message_id=result.sid,
            status=result.status,
            duration_ms=_ms_since(start),
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("whatsapp channel failed in demo fan-out")
        return ChannelResult(
            channel="whatsapp", ok=False, is_mock=False,
            error=str(exc)[:300], duration_ms=_ms_since(start),
        )


def _fire_sms(phone: str, body: str) -> ChannelResult:
    start = datetime.utcnow()
    try:
        result = sns_sms_client.send_sms(to_number=phone, body=body)
        return ChannelResult(
            channel="sms",
            ok=result.status not in ("failed",),
            is_mock=result.is_mock,
            sid_or_message_id=result.message_id,
            status=result.status,
            error=result.error_message,
            duration_ms=_ms_since(start),
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("sms channel failed in demo fan-out")
        return ChannelResult(
            channel="sms", ok=False, is_mock=False,
            error=str(exc)[:300], duration_ms=_ms_since(start),
        )


def _fire_email(email: str, subject: str, body: str) -> ChannelResult:
    start = datetime.utcnow()
    try:
        result = ses_client.send_email(to=email, subject=subject, body=body)
        return ChannelResult(
            channel="email",
            ok=result.status in ("sent", "mocked"),
            is_mock=result.is_mock,
            sid_or_message_id=result.message_id,
            status=result.status,
            error=result.error_message,
            duration_ms=_ms_since(start),
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("email channel failed in demo fan-out")
        return ChannelResult(
            channel="email", ok=False, is_mock=False,
            error=str(exc)[:300], duration_ms=_ms_since(start),
        )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/fire-all",
    response_model=FireAllResponse,
    summary="Demo: fan out voice + WA + SMS + email in parallel to the demo contacts",
)
def fire_all_channels(
    db: Session = Depends(get_db),
    _guard: None = Depends(_check_test_secret),
) -> FireAllResponse:
    started = datetime.utcnow()
    phone = _demo_phone()
    email = _demo_email()

    donor, patient, ping = _provision_demo_ping(db, phone=phone)

    # ONE Bedrock call composes voice + WA + SMS + email so all four channels
    # tell the exact same story — a judge cross-checking devices sees the
    # same LLM-written wording everywhere. Falls back to template on any
    # LLM hiccup so a Bedrock outage doesn't break the demo.
    blood_type = getattr(patient.blood_group, "value", str(patient.blood_group))
    hospital = patient.hospital or "(unspecified)"
    slot_str = (datetime.utcnow() + timedelta(days=2)).strftime("%a %d %B")
    donor_language = getattr(donor.preferred_language, "value", str(donor.preferred_language)) or "en"
    bundle: OutreachBundle = compose_outreach(
        donor_name=donor.name,
        patient_name=patient.name,
        blood_type=blood_type,
        hospital=hospital,
        slot_str=slot_str,
        language=donor_language,
    )

    # Cache the voice question against this ping so the TwiML handler reads
    # back the same LLM text when Twilio fetches /twilio/voice/twiml/ask.
    cache_voice_question(ping.id, bundle.voice_question)

    # Fan out in parallel so the four send-RPCs overlap (Twilio voice queue
    # + Twilio WA + SNS + SES all complete within ~1s rather than ~4s).
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_fire_voice, ping.id): "voice",
            pool.submit(_fire_whatsapp, phone, bundle.whatsapp_body): "whatsapp",
            pool.submit(_fire_sms, phone, bundle.sms_body): "sms",
            pool.submit(_fire_email, email, bundle.email_subject, bundle.email_body): "email",
        }
        # Preserve channel order in the response so the UI can keep the tiles
        # in a stable left-to-right layout regardless of completion order.
        results_by_channel: dict[str, ChannelResult] = {}
        for fut in as_completed(futures):
            ch = futures[fut]
            try:
                results_by_channel[ch] = fut.result()
            except Exception as exc:  # pragma: no cover
                results_by_channel[ch] = ChannelResult(
                    channel=ch, ok=False, is_mock=False, error=str(exc)[:300],
                )

    channels = [
        results_by_channel.get("voice")
        or ChannelResult(channel="voice", ok=False, is_mock=False, error="no result"),
        results_by_channel.get("whatsapp")
        or ChannelResult(channel="whatsapp", ok=False, is_mock=False, error="no result"),
        results_by_channel.get("sms")
        or ChannelResult(channel="sms", ok=False, is_mock=False, error="no result"),
        results_by_channel.get("email")
        or ChannelResult(channel="email", ok=False, is_mock=False, error="no result"),
    ]

    return FireAllResponse(
        fired_at=started,
        total_duration_ms=_ms_since(started),
        context=DemoContext(
            phone=phone,
            email=email,
            donor_id=donor.id,
            donor_name=donor.name,
            patient_id=patient.id,
            patient_name=patient.name,
            ping_id=ping.id,
        ),
        copy=OutreachCopy(
            source=bundle.source,
            model=bundle.model,
            voice_question=bundle.voice_question,
            whatsapp_body=bundle.whatsapp_body,
            sms_body=bundle.sms_body,
            email_subject=bundle.email_subject,
            email_body=bundle.email_body,
            tokens_in=bundle.tokens_in,
            tokens_out=bundle.tokens_out,
        ),
        channels=channels,
    )


@router.get(
    "/contacts",
    summary="Read the currently-active demo contact target (lets the UI display 'will ping +91...')",
)
def get_demo_contacts() -> dict[str, str]:
    return {"phone": _demo_phone(), "email": _demo_email()}
