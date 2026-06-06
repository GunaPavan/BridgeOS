"""Phase B — automated follow-up dispatcher.

Single source of truth for the three follow-up messages that the automation
engine ticks against ``OutreachPing`` rows:

  - ``send_pending_nudge``         (template: pending_ping_nudge)
  - ``send_pre_donation_reminder`` (template: pre_donation_reminder)
  - ``send_post_donation_thank_you`` (template: post_donation_thank_you)

Each helper:
  1. Loads the donor + patient and renders the template in the donor's
     language (falls back to English via the registry).
  2. Calls ``twilio_client.send_whatsapp`` — quiet hours are the CALLER's
     job (the scheduler skips ticks during quiet windows so we don't bury
     this check inside every dispatcher).
  3. Mirrors the outbound message into ``WhatsAppMessage`` so it appears in
     the /whatsapp threads UI.
  4. Stamps the ping with the appropriate timestamp so the job's idempotency
     guard never double-sends.

These functions return a boolean — True if a message went out, False if
something stopped it (donor missing, patient missing, send failure). The
scheduler jobs aggregate the booleans into ``items_processed``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.integrations import twilio_client
from app.models import (
    Bridge,
    Donor,
    MessageDirection,
    MessageStatus,
    OutreachPing,
    OutreachWave,
    Patient,
    WhatsAppMessage,
)
from app.services import whatsapp_templates as _tmpl

logger = logging.getLogger(__name__)


# Tuning constants — referenced both by the dispatcher and the jobs so the
# tests can monkey-patch one place and have the other agree.
NUDGE_PENDING_AFTER_HOURS = 4    # how long a PENDING ping must wait before we nudge
NUDGE_MIN_GAP_HOURS = 12         # min gap between successive nudges to the same ping
NUDGE_MAX_PER_PING = 2           # hard cap so we never spam
DONOR_DEFERRAL_DAYS = 90         # clinical deferral — drives next_eligible_date


def _donor_first_name(donor: Donor) -> str:
    return (donor.name.split()[0] if donor.name else "there")


def _render_and_send(
    *,
    db: Session,
    ping: OutreachPing,
    donor: Donor,
    patient: Patient,
    wave: OutreachWave,
    template_key: str,
    extra_vars: dict[str, object],
    now: datetime,
) -> bool:
    """Shared body for all three follow-ups.

    Returns True on send (Twilio accepted + WhatsAppMessage row written).
    Returns False on any failure (donor missing phone, render error,
    Twilio raise). Failures are logged but never raise — the job stays
    green.
    """
    if not donor.phone:
        logger.info(
            "Skipping %s for ping %s — donor %s has no phone",
            template_key, ping.id, donor.id,
        )
        return False

    lang = ping.language or getattr(
        donor.preferred_language, "value", str(donor.preferred_language)
    )

    try:
        rendered = _tmpl.render(
            template_key,
            language=lang,
            donor_first=_donor_first_name(donor),
            donor_name=donor.name or "",
            patient_name=patient.name or "",
            patient_age=patient.age or 0,
            patient_blood_group=getattr(
                patient.blood_group, "value", str(patient.blood_group)
            ),
            slot_date=wave.slot_date.isoformat() if wave.slot_date else "",
            **{k: str(v) if v is not None else "" for k, v in extra_vars.items()},
        )
    except Exception:  # pragma: no cover — defensive
        logger.exception(
            "Render failed for template=%s ping=%s lang=%s",
            template_key, ping.id, lang,
        )
        return False

    try:
        send_result = twilio_client.send_whatsapp(
            to_number=donor.phone, body=rendered.body
        )
    except Exception:  # pragma: no cover — defensive
        logger.exception(
            "Twilio send failed for template=%s ping=%s", template_key, ping.id
        )
        return False

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
    return True


# ---------------------------------------------------------------------------
# 1) Pending-ping nudge
# ---------------------------------------------------------------------------


def send_pending_nudge(
    db: Session, *, ping: OutreachPing, now: Optional[datetime] = None
) -> bool:
    """Send the soft "still hoping to hear back" nudge. Stamps the ping.

    Returns True if a message went out.
    """
    now = now or datetime.utcnow()
    donor = db.get(Donor, ping.donor_id)
    wave = db.get(OutreachWave, ping.wave_id)
    if donor is None or wave is None:
        return False
    patient = db.get(Patient, wave.patient_id)
    if patient is None:
        return False

    sent = _render_and_send(
        db=db,
        ping=ping,
        donor=donor,
        patient=patient,
        wave=wave,
        template_key="pending_ping_nudge",
        extra_vars={},
        now=now,
    )
    if sent:
        ping.nudge_count = (ping.nudge_count or 0) + 1
        ping.last_nudge_at = now
    return sent


# ---------------------------------------------------------------------------
# 2) Pre-donation reminder
# ---------------------------------------------------------------------------


def _hospital_for(patient: Patient) -> str:
    """Show "(unspecified)" if hospital field is empty so the message never
    renders 'at  on …' with a double space."""
    h = patient.hospital or "the hospital"
    return h if h.strip() else "the hospital"


def send_pre_donation_reminder(
    db: Session, *, ping: OutreachPing, now: Optional[datetime] = None
) -> bool:
    """Send the day-before commitment reminder. Stamps the ping."""
    now = now or datetime.utcnow()
    donor = db.get(Donor, ping.donor_id)
    wave = db.get(OutreachWave, ping.wave_id)
    if donor is None or wave is None:
        return False
    patient = db.get(Patient, wave.patient_id)
    if patient is None:
        return False

    sent = _render_and_send(
        db=db,
        ping=ping,
        donor=donor,
        patient=patient,
        wave=wave,
        template_key="pre_donation_reminder",
        extra_vars={"hospital": _hospital_for(patient)},
        now=now,
    )
    if sent:
        ping.reminder_sent_at = now
    return sent


# ---------------------------------------------------------------------------
# 3) Post-donation thank-you
# ---------------------------------------------------------------------------


def _next_eligible(donor: Donor) -> Optional[date]:
    """donor.last_donation_date + 90d, or today + 90d if not set."""
    base = donor.last_donation_date or date.today()
    return base + timedelta(days=DONOR_DEFERRAL_DAYS)


def send_post_donation_thank_you(
    db: Session, *, ping: OutreachPing, now: Optional[datetime] = None
) -> bool:
    """Send the post-donation thank-you with next eligible date. Stamps the ping."""
    now = now or datetime.utcnow()
    donor = db.get(Donor, ping.donor_id)
    wave = db.get(OutreachWave, ping.wave_id)
    if donor is None or wave is None:
        return False
    patient = db.get(Patient, wave.patient_id)
    if patient is None:
        return False

    next_elig = _next_eligible(donor)
    sent = _render_and_send(
        db=db,
        ping=ping,
        donor=donor,
        patient=patient,
        wave=wave,
        template_key="post_donation_thank_you",
        extra_vars={"next_eligible_date": next_elig.isoformat() if next_elig else ""},
        now=now,
    )
    if sent:
        ping.thank_you_sent_at = now
    return sent
