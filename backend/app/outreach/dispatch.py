"""Phase C — push waves out over WhatsApp, close them on donor reply.

Responsibilities:

    dispatch_wave(wave)                — render + send a ping per donor in
                                         the wave, respecting quiet hours,
                                         tagging each WhatsApp with a slot
                                         reference token so the webhook can
                                         route the reply back to the right
                                         (wave, donor) pair
    confirm_outreach_acceptance(...)   — donor said YES: mark wave ACCEPTED,
                                         silently cancel sibling pings, set
                                         a 90-day clinical cooldown on the
                                         accepting donor
    record_outreach_decline(...)       — donor said NO: per-patient 30-day cooldown
    expire_pending_pings(...)          — wave expired: any still-PENDING pings
                                         become NO_REPLY with a 7-day cooldown
    is_quiet_hours(now)                — 22:00–07:00 IST → suppress (overridable
                                         in EMERGENCY tier)
    parse_slot_ref(text)               — pull a slot reference out of an inbound
                                         message body so the webhook can correlate
                                         the reply to the wave that asked
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.integrations import twilio_client
from app.models import (
    BridgeMembership,
    CooldownReason,
    Donor,
    MembershipRole,
    MembershipStatus,
    MessageDirection,
    MessageStatus,
    OutreachCooldown,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    PingResponse,
    WhatsAppMessage,
)
from app.services import whatsapp_templates as _tmpl

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Quiet hours
# ---------------------------------------------------------------------------

IST_OFFSET_HOURS = 5.5
QUIET_START_HOUR_IST = 22  # 10 pm
QUIET_END_HOUR_IST = 7     # 7 am


def is_quiet_hours(now: Optional[datetime] = None) -> bool:
    """True if right now is inside the 22:00–07:00 IST suppression window.

    Emergency tier callers should pass ``override_quiet_hours=True`` instead
    of asking — this helper is the unambiguous "is it polite?" check.
    """
    now = now or datetime.utcnow()
    # Convert to IST
    ist = now + timedelta(hours=IST_OFFSET_HOURS)
    hr = ist.hour
    if QUIET_START_HOUR_IST <= QUIET_END_HOUR_IST:
        return QUIET_START_HOUR_IST <= hr < QUIET_END_HOUR_IST
    # window spans midnight (22-07)
    return hr >= QUIET_START_HOUR_IST or hr < QUIET_END_HOUR_IST


# ---------------------------------------------------------------------------
# Slot reference token — correlates inbound WhatsApp replies to (wave, donor)
# ---------------------------------------------------------------------------

# The reference is the first 8 hex chars of the OutreachPing.id. Including it
# inside the rendered message body lets the webhook look up the exact ping
# the donor is responding to even when they reply long after the message
# was sent and we've also asked them about other patients in between.
_SLOT_REF_RE = re.compile(r"\bref\s+([0-9a-f]{8})\b", flags=re.IGNORECASE)


def make_slot_ref(ping_id: uuid.UUID) -> str:
    return ping_id.hex[:8]


def parse_slot_ref(text: str) -> Optional[str]:
    """Extract a slot reference token (8 hex chars) from a message body.

    The webhook calls this on every inbound — when it returns a value the
    handler knows the message is a wave reply, not a generic recruit answer.
    """
    if not text:
        return None
    m = _SLOT_REF_RE.search(text)
    return m.group(1).lower() if m else None


# ---------------------------------------------------------------------------
# Wave dispatch — render + send + persist
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DispatchSummary:
    wave_id: uuid.UUID
    pings_sent: int
    pings_suppressed_quiet_hours: int
    pings_failed: int


def dispatch_wave(
    wave: OutreachWave,
    *,
    db: Session,
    override_quiet_hours: bool = False,
    now: Optional[datetime] = None,
) -> DispatchSummary:
    """Send every PENDING ping in this wave via WhatsApp.

    Per ping the function:
      1. Suppresses if quiet hours are active and we're not overriding
      2. Loads the donor + patient
      3. Renders the urgent_slot_alert template in the donor's preferred language
      4. Calls twilio_client.send_whatsapp; stores the SID + status
      5. Writes a WhatsAppMessage outbound row (so it appears on /whatsapp threads)

    The wave's status stays ACTIVE — only the PINGS get sent. Phase C close
    handlers below flip wave status on acceptance / expiry.
    """
    now = now or datetime.utcnow()
    sent = 0
    suppressed = 0
    failed = 0

    quiet = is_quiet_hours(now) and not override_quiet_hours
    patient = db.get(Patient, wave.patient_id)
    if patient is None:
        raise ValueError(f"Wave {wave.id} references missing patient {wave.patient_id}")

    template_key = "urgent_slot_alert"
    for ping in wave.pings:
        if ping.response != PingResponse.PENDING:
            continue
        donor = db.get(Donor, ping.donor_id)
        if donor is None:
            ping.response = PingResponse.CANCELLED
            ping.response_at = now
            failed += 1
            continue

        if quiet:
            # Don't send; leave ping PENDING with a marker so the next non-quiet
            # cycle picks it up. We bump expires_at out so the wave doesn't auto-
            # expire mid-quiet-window.
            ping.expires_at = max(
                ping.expires_at or now, now + timedelta(hours=2)
            )
            suppressed += 1
            continue

        lang = ping.language or getattr(
            donor.preferred_language, "value", str(donor.preferred_language)
        )
        rendered = _tmpl.render(
            template_key,
            language=lang,
            donor_first=(donor.name.split()[0] if donor.name else "there"),
            donor_name=donor.name,
            patient_name=patient.name,
            patient_age=patient.age,
            patient_blood_group=getattr(
                patient.blood_group, "value", str(patient.blood_group)
            ),
            slot_date=wave.slot_date.isoformat(),
            slot_ref=make_slot_ref(ping.id),
        )

        # Phase E3: enqueue the dispatch to SQS instead of calling Twilio
        # inline. The DispatchWorker thread drains the queue and stamps the
        # ping + WhatsAppMessage row. This decouples allocator latency from
        # Twilio API latency. Set BRIDGE_OS_DISPATCH_INLINE=1 to keep the
        # legacy synchronous behaviour (useful when running scripts without
        # the scheduler runtime active — re-ingest, tests, etc.).
        import os as _os

        if _os.getenv("BRIDGE_OS_DISPATCH_INLINE") == "1":
            try:
                send_result = twilio_client.send_whatsapp(
                    to_number=donor.phone, body=rendered.body
                )
            except Exception:  # pragma: no cover
                logger.exception("Twilio send failed for ping %s", ping.id)
                failed += 1
                continue

            ping.whatsapp_sid = send_result.sid
            ping.language = rendered.language_used
            ping.template_key = template_key
            ping.sent_at = now

            try:
                outbound_status = (
                    MessageStatus(send_result.status)
                    if send_result.status in {s.value for s in MessageStatus}
                    else MessageStatus.QUEUED
                )
                db.add(
                    WhatsAppMessage(
                        donor_id=donor.id,
                        bridge_id=wave.bridge_id,
                        direction=MessageDirection.OUTBOUND,
                        from_number=twilio_client.whatsapp_from(),
                        to_number=donor.phone,
                        body=rendered.body,
                        status=outbound_status,
                        twilio_sid=send_result.sid,
                        template_key=template_key,
                        language=rendered.language_used,
                    )
                )
            except Exception:  # pragma: no cover
                logger.exception("Failed to mirror outreach ping into WhatsAppMessage")
            sent += 1
        else:
            from app.outreach.dispatch_queue import DispatchEnvelope, enqueue_dispatch

            ping.template_key = template_key
            ping.language = rendered.language_used
            # ping.sent_at is set by the worker once it actually ships

            # E6: route by donor's preferred_channel. Default = WhatsApp
            # because it's the only bidirectional channel — donor replies
            # come back through the Twilio webhook and feed the automation
            # loop (classify intent → cooldown / re-fire). SMS is opt-in
            # only (one-way; SNS direct-publish can't receive replies
            # without DLT-registered numbers in India). Email is
            # caregiver-only, never donor.
            channel = getattr(
                donor.preferred_channel, "value", str(donor.preferred_channel)
            ) if donor.preferred_channel else "whatsapp"
            if channel == "email":
                # Donor accidentally set to email — emails are caregiver-only.
                channel = "whatsapp"

            try:
                enqueue_dispatch(
                    DispatchEnvelope(
                        channel=channel,
                        to=donor.phone,
                        body=rendered.body,
                        idempotency_key=f"dispatch_{ping.id}",
                        ping_id=str(ping.id),
                        template_key=template_key,
                        language=rendered.language_used,
                        donor_id=str(donor.id),
                    )
                )
                sent += 1
            except Exception:  # pragma: no cover
                logger.exception("Failed to enqueue dispatch for ping %s", ping.id)
                failed += 1

    # Stamp the donor.last_contacted_date so the eligibility filter respects the
    # 7-day social cooldown on the next cycle.
    for ping in wave.pings:
        if ping.response == PingResponse.PENDING and ping.whatsapp_sid:
            donor = db.get(Donor, ping.donor_id)
            if donor is not None:
                donor.last_contacted_date = now.date()
                donor.total_calls = (donor.total_calls or 0) + 1

    db.flush()
    return DispatchSummary(
        wave_id=wave.id,
        pings_sent=sent,
        pings_suppressed_quiet_hours=suppressed,
        pings_failed=failed,
    )


# ---------------------------------------------------------------------------
# Acceptance / decline / expiry close handlers
# ---------------------------------------------------------------------------


def _find_pending_ping_by_slot_ref(
    db: Session, *, donor_id: uuid.UUID, slot_ref: str
) -> Optional[OutreachPing]:
    """Look up a still-PENDING ping for this donor whose id starts with the ref."""
    stmt = select(OutreachPing).where(
        and_(
            OutreachPing.donor_id == donor_id,
            OutreachPing.response == PingResponse.PENDING,
        )
    )
    candidates = db.execute(stmt).scalars().all()
    for p in candidates:
        if p.id.hex[:8].lower() == slot_ref.lower():
            return p
    return None


def confirm_outreach_acceptance(
    db: Session,
    *,
    donor_id: uuid.UUID,
    slot_ref: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Optional[OutreachWave]:
    """Donor said YES.

    1. Find the matching PENDING ping (by slot_ref if present; otherwise pick
       the donor's most recent PENDING ping)
    2. Mark that ping ACCEPTED
    3. Flip the wave to ACCEPTED and record the donor
    4. Cancel all other still-PENDING pings for the same wave (silent close;
       no notification — the other donors didn't engage yet)
    5. Insert a 90-day RECENT_DONATION cooldown so the allocator skips this
       donor through their clinical recovery window
    6. Move the donor into ACTIVE membership on the patient's bridge if they
       weren't already (PENDING memberships from the recruit flow stay separate;
       outreach is for an *existing* cohort fill-in, not a new recruit)

    Returns the wave that was accepted, or None if no matching ping was found.
    """
    now = now or datetime.utcnow()

    ping: Optional[OutreachPing] = None
    if slot_ref:
        ping = _find_pending_ping_by_slot_ref(db, donor_id=donor_id, slot_ref=slot_ref)
    if ping is None:
        # Fallback: most recent PENDING ping for this donor
        stmt = (
            select(OutreachPing)
            .where(
                and_(
                    OutreachPing.donor_id == donor_id,
                    OutreachPing.response == PingResponse.PENDING,
                )
            )
            .order_by(OutreachPing.sent_at.desc())
            .limit(1)
        )
        ping = db.execute(stmt).scalar_one_or_none()
    if ping is None:
        return None

    wave = db.get(OutreachWave, ping.wave_id)
    if wave is None:
        return None

    # 1) Mark winning ping
    ping.response = PingResponse.ACCEPTED
    ping.response_at = now

    # 2) Wave is now ACCEPTED
    wave.status = OutreachWaveStatus.ACCEPTED
    wave.resolved_at = now
    wave.resolved_by_donor_id = donor_id

    # 3) Cancel siblings (silent — no notification)
    for sibling in wave.pings:
        if sibling.id == ping.id:
            continue
        if sibling.response == PingResponse.PENDING:
            sibling.response = PingResponse.CANCELLED
            sibling.response_at = now

    # 4) 90-day clinical cooldown for the accepting donor (global — applies to
    # every patient, not just this one, since the deferral is about donor health)
    db.add(
        OutreachCooldown(
            donor_id=donor_id,
            patient_id=None,
            reason=CooldownReason.RECENT_DONATION,
            expires_at=now + timedelta(days=90),
            notes=f"accepted wave {wave.id} for slot {wave.slot_date}",
        )
    )

    # 5) Slot the donor into the patient's bridge as PRIMARY if they aren't
    # already an active member. The recruit flow (G1) handles brand-new bridge
    # joins via PENDING; this path is for a donor already in the cohort
    # confirming their next-slot commitment. We just record the ACTIVE
    # membership if missing — the existing scheduler picks it up next cycle.
    if wave.bridge_id:
        existing = db.execute(
            select(BridgeMembership).where(
                and_(
                    BridgeMembership.bridge_id == wave.bridge_id,
                    BridgeMembership.donor_id == donor_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                BridgeMembership(
                    bridge_id=wave.bridge_id,
                    donor_id=donor_id,
                    role=MembershipRole.PRIMARY,
                    status=MembershipStatus.ACTIVE,
                )
            )
        elif existing.status != MembershipStatus.ACTIVE:
            existing.status = MembershipStatus.ACTIVE

    # 6) Caregiver notification — if the patient has a caregiver phone on
    # file, send the multilingual `transfusion_confirmed_caregiver` template
    # so the family knows who's covering the next transfusion. Failure here
    # is non-fatal — the wave still closes.
    try:
        patient = db.get(Patient, wave.patient_id)
        donor = db.get(Donor, donor_id)
        if (
            patient is not None
            and patient.caregiver_phone
            and donor is not None
        ):
            caregiver_first = (patient.caregiver_name or patient.name).split()[0]
            caregiver_lang = getattr(
                patient.preferred_language, "value", str(patient.preferred_language)
            ) or "en"
            rendered = _tmpl.render(
                "transfusion_confirmed_caregiver",
                language=caregiver_lang,
                caregiver_first=caregiver_first,
                patient_name=patient.name,
                added_donor_name=donor.name,
                next_transfusion_date=wave.slot_date.isoformat(),
            )
            send_result = twilio_client.send_whatsapp(
                to_number=patient.caregiver_phone, body=rendered.body
            )
            db.add(
                WhatsAppMessage(
                    bridge_id=wave.bridge_id,
                    direction=MessageDirection.OUTBOUND,
                    from_number=twilio_client.whatsapp_from(),
                    to_number=patient.caregiver_phone,
                    body=rendered.body,
                    status=(
                        MessageStatus(send_result.status)
                        if send_result.status in {s.value for s in MessageStatus}
                        else MessageStatus.QUEUED
                    ),
                    twilio_sid=send_result.sid,
                    template_key="transfusion_confirmed_caregiver",
                    language=rendered.language_used,
                )
            )
    except Exception:  # pragma: no cover — caregiver ping shouldn't block accept
        logger.exception("Failed to send caregiver confirmation on accept")

    db.flush()
    return wave


def cancel_outreach_acceptance(
    db: Session,
    *,
    donor_id: uuid.UUID,
    wave_id: Optional[uuid.UUID] = None,
    now: Optional[datetime] = None,
) -> Optional[OutreachWave]:
    """Donor who previously accepted now says they can't make it.

    Reverses ``confirm_outreach_acceptance``:
      1. Latest ACCEPTED wave where this donor was the resolver
      2. Flip wave status back to ACTIVE (so the cycle picks it up next round)
      3. Mark the donor's ping from ACCEPTED → DECLINED
      4. Drop the 90-day clinical cooldown (they're not actually donating)
      5. Add a 30-day per-patient cooldown (donor declined this specific slot)
      6. Leave the bridge membership as-is — the donor may still be in the
         cohort, just not for THIS slot

    Returns the wave that was un-accepted, or None if no match was found.
    """
    now = now or datetime.utcnow()

    wave: Optional[OutreachWave] = None
    if wave_id is not None:
        wave = db.get(OutreachWave, wave_id)
    if wave is None:
        # Find the most recent ACCEPTED wave where this donor was the resolver
        stmt = (
            select(OutreachWave)
            .where(
                and_(
                    OutreachWave.resolved_by_donor_id == donor_id,
                    OutreachWave.status == OutreachWaveStatus.ACCEPTED,
                )
            )
            .order_by(OutreachWave.resolved_at.desc())
            .limit(1)
        )
        wave = db.execute(stmt).scalar_one_or_none()
    if wave is None:
        return None

    # 1) Reverse wave status
    wave.status = OutreachWaveStatus.ACTIVE
    wave.resolved_at = None
    wave.resolved_by_donor_id = None

    # 2) Flip the donor's ping from ACCEPTED -> DECLINED
    for ping in wave.pings:
        if ping.donor_id == donor_id and ping.response == PingResponse.ACCEPTED:
            ping.response = PingResponse.DECLINED
            ping.response_at = now

    # 3) Drop the 90-day clinical cooldown that was added on accept
    stmt = select(OutreachCooldown).where(
        and_(
            OutreachCooldown.donor_id == donor_id,
            OutreachCooldown.reason == CooldownReason.RECENT_DONATION,
            OutreachCooldown.patient_id.is_(None),
        )
    )
    for cd in db.execute(stmt).scalars().all():
        db.delete(cd)

    # 4) Per-patient 30-day decline cooldown
    db.add(
        OutreachCooldown(
            donor_id=donor_id,
            patient_id=wave.patient_id,
            reason=CooldownReason.DECLINED,
            expires_at=now + timedelta(days=30),
            notes=f"cancelled prior acceptance of wave {wave.id}",
        )
    )

    db.flush()
    return wave


def record_outreach_decline(
    db: Session,
    *,
    donor_id: uuid.UUID,
    slot_ref: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Optional[OutreachPing]:
    """Donor said NO.

    Mark the matching ping as DECLINED. Insert a 30-day per-patient cooldown
    so the allocator doesn't pester this donor about the same patient again,
    but stays free to ask them about OTHER patients next cycle (they declined
    this one slot, not this entire relationship).
    """
    now = now or datetime.utcnow()
    ping: Optional[OutreachPing] = None
    if slot_ref:
        ping = _find_pending_ping_by_slot_ref(db, donor_id=donor_id, slot_ref=slot_ref)
    if ping is None:
        stmt = (
            select(OutreachPing)
            .where(
                and_(
                    OutreachPing.donor_id == donor_id,
                    OutreachPing.response == PingResponse.PENDING,
                )
            )
            .order_by(OutreachPing.sent_at.desc())
            .limit(1)
        )
        ping = db.execute(stmt).scalar_one_or_none()
    if ping is None:
        return None

    ping.response = PingResponse.DECLINED
    ping.response_at = now

    wave = db.get(OutreachWave, ping.wave_id)
    if wave is not None:
        db.add(
            OutreachCooldown(
                donor_id=donor_id,
                patient_id=wave.patient_id,
                reason=CooldownReason.DECLINED,
                expires_at=now + timedelta(days=30),
                notes=f"declined wave {wave.id} for slot {wave.slot_date}",
            )
        )
    db.flush()
    return ping


def expire_pending_pings(
    db: Session,
    *,
    wave_id: uuid.UUID,
    now: Optional[datetime] = None,
) -> int:
    """Wave's expiry passed → mark every PENDING ping NO_REPLY + 7-day cooldown.

    Returns the count of pings flipped. Called by the cycle's expiry sweep
    OR explicitly when a wave is force-cancelled by a coordinator.
    """
    now = now or datetime.utcnow()
    stmt = select(OutreachPing).where(
        and_(
            OutreachPing.wave_id == wave_id,
            OutreachPing.response == PingResponse.PENDING,
        )
    )
    pings = db.execute(stmt).scalars().all()
    for ping in pings:
        ping.response = PingResponse.NO_REPLY
        ping.response_at = now
        # 7-day global cooldown so the donor is still eligible for OTHER
        # patients in a week but isn't re-pinged for this one anytime soon
        db.add(
            OutreachCooldown(
                donor_id=ping.donor_id,
                patient_id=None,
                reason=CooldownReason.NO_REPLY,
                expires_at=now + timedelta(days=7),
                notes=f"no-reply on wave {wave_id}",
            )
        )
    db.flush()
    return len(pings)
