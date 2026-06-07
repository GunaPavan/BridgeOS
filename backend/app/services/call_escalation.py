"""E11 — tiered call escalation.

Scans ACTIVE OutreachWaves for ones that have aged past their
urgency-tier threshold without any accept. For each match, creates a
CallEscalation row + dispatches the coordinator alert.

THRESHOLDS (configurable via env / settings):
    CRITICAL → 2 hours  — patient needs blood today/tomorrow
    HIGH     → 24 hours — within the week
    MEDIUM   → 3 days   — 1-2 weeks out
    PLANNED  → 5 days   — >2 weeks out (user's original suggestion)

These reflect Blood Bridge clinical reality: 18-21 day transfusion cycle,
~7 days of effective recruitment time per slot.

CHANNEL POLICY:
    All escalations: SMS the coordinator (SNS direct-publish).
    CRITICAL + HIGH: also place a Twilio Voice call.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.integrations import sns_sms_client, twilio_client
from app.models import (
    CallEscalation,
    EscalationChannel,
    EscalationStatus,
    OutreachPing,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    PingResponse,
    UrgencyTier,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configurable thresholds (env var overrides)
# ---------------------------------------------------------------------------


def _threshold_hours(tier: UrgencyTier) -> int:
    """Hours of no-response before an escalation is triggered."""
    overrides = {
        UrgencyTier.CRITICAL: ("BRIDGE_OS_ESCALATE_CRITICAL_HOURS", 2),
        UrgencyTier.HIGH: ("BRIDGE_OS_ESCALATE_HIGH_HOURS", 24),
        UrgencyTier.MEDIUM: ("BRIDGE_OS_ESCALATE_MEDIUM_HOURS", 72),
        UrgencyTier.PLANNED: ("BRIDGE_OS_ESCALATE_PLANNED_HOURS", 120),  # 5 days
    }
    env_var, default = overrides[tier]
    try:
        return int(os.environ.get(env_var, default))
    except ValueError:
        return default


def _wants_voice(tier: UrgencyTier) -> bool:
    """Voice call only for the urgent tiers — coordinator's phone shouldn't
    ring at 2am for a PLANNED-tier escalation."""
    return tier in (UrgencyTier.CRITICAL, UrgencyTier.HIGH)


def _coordinator_phone() -> str:
    """E.164 number we call/text for escalations. Override via env."""
    return os.environ.get("BRIDGE_OS_COORDINATOR_PHONE", "REDACTED-PHONE")


def _public_base_url() -> Optional[str]:
    """Public origin of THIS backend. Used as the base for TwiML callback
    URLs the donor's voice call hits. Returns None in dev (localhost)."""
    return os.environ.get("BRIDGE_OS_PUBLIC_URL")


# ---------------------------------------------------------------------------
# Scanner — finds waves that need escalation
# ---------------------------------------------------------------------------


@dataclass
class EscalationCandidate:
    wave: OutreachWave
    patient: Patient
    hours_since_dispatch: int
    pings_sent: int
    pings_no_response: int


def find_escalation_candidates(db: Session, *, now: Optional[datetime] = None) -> list[EscalationCandidate]:
    """Scan for ACTIVE waves where (a) age > urgency threshold AND
    (b) zero pings accepted AND (c) no existing PENDING/DISPATCHED escalation.
    """
    now = now or datetime.utcnow()
    candidates: list[EscalationCandidate] = []

    # All active waves
    active_waves = (
        db.execute(
            select(OutreachWave).where(
                OutreachWave.status == OutreachWaveStatus.ACTIVE
            )
        )
        .scalars()
        .all()
    )

    for wave in active_waves:
        # Skip if there's already a pending/dispatched escalation for this wave
        existing = (
            db.execute(
                select(CallEscalation).where(
                    and_(
                        CallEscalation.wave_id == wave.id,
                        CallEscalation.status.in_(
                            [EscalationStatus.PENDING, EscalationStatus.DISPATCHED]
                        ),
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            continue

        # Age check (using created_at — proxy for when outreach started)
        tier_val = getattr(wave.urgency, "value", str(wave.urgency))
        try:
            tier = UrgencyTier(tier_val)
        except ValueError:
            tier = UrgencyTier.MEDIUM
        threshold_hours = _threshold_hours(tier)
        age_hours = (now - wave.created_at).total_seconds() / 3600
        if age_hours < threshold_hours:
            continue

        # Accept gate: any donor in this wave accepted? Skip.
        accepted = sum(
            1 for p in wave.pings if p.response == PingResponse.ACCEPTED
        )
        if accepted > 0:
            continue

        # ``sent_at`` is NOT NULL in the OutreachPing schema, so any ping
        # row IS a dispatched ping.
        pings_sent = len(wave.pings)
        if pings_sent == 0:
            continue  # wave with zero pings = nothing to escalate

        no_response = sum(
            1 for p in wave.pings if p.response in (PingResponse.PENDING, PingResponse.NO_REPLY)
        )

        patient = db.get(Patient, wave.patient_id)
        if patient is None:
            continue

        candidates.append(
            EscalationCandidate(
                wave=wave,
                patient=patient,
                hours_since_dispatch=int(age_hours),
                pings_sent=pings_sent,
                pings_no_response=no_response,
            )
        )

    return candidates


# ---------------------------------------------------------------------------
# Dispatcher — sends the actual SMS/voice alert
# ---------------------------------------------------------------------------


def _format_sms(c: EscalationCandidate) -> str:
    p = c.patient
    return (
        f"BRIDGE OS ESCALATION ({c.wave.urgency.value if hasattr(c.wave.urgency, 'value') else c.wave.urgency}): "
        f"{p.name} (B{p.blood_group}) needs a donor at {p.hospital}. "
        f"{c.pings_sent} donors contacted, {c.pings_no_response} have not responded in "
        f"{c.hours_since_dispatch}h. Please call them now or open Bridge OS."
    )


def _format_voice(c: EscalationCandidate) -> str:
    p = c.patient
    tier_word = getattr(c.wave.urgency, "value", str(c.wave.urgency)).replace("_", " ")
    return (
        f"Bridge O S {tier_word} escalation. "
        f"Patient {p.name}, blood type B {p.blood_group}, at {p.hospital}. "
        f"{c.pings_sent} donors contacted, {c.pings_no_response} have not responded in "
        f"{c.hours_since_dispatch} hours. "
        f"Please open Bridge O S and contact donors manually."
    )


def dispatch_escalation(db: Session, candidate: EscalationCandidate) -> CallEscalation:
    """Create the CallEscalation row + send SMS (+ voice if urgent)."""
    tier_val = getattr(candidate.wave.urgency, "value", str(candidate.wave.urgency))
    try:
        tier = UrgencyTier(tier_val)
    except ValueError:
        tier = UrgencyTier.MEDIUM

    esc = CallEscalation(
        wave_id=candidate.wave.id,
        patient_id=candidate.patient.id,
        urgency_at_trigger=tier_val,
        hours_since_dispatch=candidate.hours_since_dispatch,
        pings_sent=candidate.pings_sent,
        pings_no_response=candidate.pings_no_response,
        coordinator_phone=_coordinator_phone(),
        status=EscalationStatus.PENDING,
    )
    db.add(esc)
    db.flush()

    # 1. Always send SMS via SNS direct-publish
    sms_body = _format_sms(candidate)
    sms_result = sns_sms_client.send_sms(
        to_number=_coordinator_phone(), body=sms_body
    )
    esc.sms_message_id = sms_result.message_id

    # 2. Voice call ONLY for urgent tiers
    voice_sid: Optional[str] = None
    if _wants_voice(tier):
        voice_body = _format_voice(candidate)
        voice_result = twilio_client.place_voice_call(
            to_number=_coordinator_phone(), message=voice_body
        )
        voice_sid = voice_result.sid
        esc.voice_call_sid = voice_sid
        esc.channel = EscalationChannel.SMS_AND_VOICE
    else:
        esc.channel = EscalationChannel.SMS

    esc.status = EscalationStatus.DISPATCHED
    esc.dispatched_at = datetime.utcnow()
    db.flush()
    logger.info(
        "Escalation dispatched: patient=%s, tier=%s, sms=%s, voice=%s",
        candidate.patient.name, tier_val, sms_result.message_id, voice_sid,
    )
    return esc


def run_escalation_scan(db: Session, *, now: Optional[datetime] = None) -> dict:
    """Scheduler entry point — find candidates and dispatch each one.

    Returns a summary the scheduler logs into ScheduledJobRun.
    """
    candidates = find_escalation_candidates(db, now=now)
    dispatched = 0
    failed = 0
    for c in candidates:
        try:
            dispatch_escalation(db, c)
            dispatched += 1
        except Exception:  # pragma: no cover
            logger.exception("Escalation dispatch failed for wave %s", c.wave.id)
            failed += 1
    db.commit()
    return {
        "candidates_found": len(candidates),
        "dispatched": dispatched,
        "failed": failed,
    }
