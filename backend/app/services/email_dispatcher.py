"""High-level email dispatcher.

One function per template — render + send via SES + persist EmailMessage row.
The scheduler job (`auto_caregiver_email_digest`) loops and calls these. The
webhook (Twilio failure → SES fallback) calls
``send_caregiver_emergency_alert``.

Every dispatcher returns a ``DispatchOutcome`` boolean wrapper so callers can
aggregate "how many sent, how many failed" without inspecting raw SES API
results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.integrations import ses_client
from app.models import EmailMessage, Patient
from app.services import email_templates as _tmpl

logger = logging.getLogger(__name__)


@dataclass
class DispatchOutcome:
    sent: bool
    message_id: str
    is_mock: bool
    status: str
    error_message: Optional[str] = None


def _persist_and_send(
    db: Session,
    *,
    to: str,
    subject: str,
    body: str,
    template_key: str,
    donor_id=None,
    caregiver_for_patient_id=None,
) -> DispatchOutcome:
    """Common path: SES call + EmailMessage row."""
    result = ses_client.send_email(to=to, subject=subject, body=body)
    now = datetime.utcnow()
    row = EmailMessage(
        direction="outbound",
        recipient_email=to,
        from_email=ses_client.from_email(),
        subject=subject,
        body=body,
        template_key=template_key,
        language="en",
        ses_message_id=result.message_id,
        status=result.status,
        is_mock=result.is_mock,
        error_message=result.error_message,
        donor_id=donor_id,
        caregiver_for_patient_id=caregiver_for_patient_id,
        created_at=now,
        sent_at=now if result.status in ("sent", "mocked") else None,
    )
    db.add(row)
    db.flush()
    return DispatchOutcome(
        sent=(result.status in ("sent", "mocked")),
        message_id=result.message_id,
        is_mock=result.is_mock,
        status=result.status,
        error_message=result.error_message,
    )


# ---------------------------------------------------------------------------
# Daily digest
# ---------------------------------------------------------------------------


def send_caregiver_daily_digest(
    db: Session, *, patient: Patient
) -> DispatchOutcome:
    """Render + send the calm daily summary to the patient's caregiver."""
    if not patient.caregiver_email:
        return DispatchOutcome(
            sent=False, message_id="", is_mock=True, status="skipped",
            error_message="no caregiver_email",
        )

    bridge = patient.bridge
    active_donors = bridge.active_donor_count if bridge else 0
    health_label = (
        getattr(bridge.health, "value", str(bridge.health)) if bridge else "no bridge"
    )

    rendered = _tmpl.render_caregiver_daily_digest(
        caregiver_first=(patient.caregiver_name or "there").split()[0],
        patient_name=patient.name or "your patient",
        next_transfusion_date=patient.next_transfusion_date,
        days_until=patient.days_until_transfusion,
        active_donor_count=active_donors,
        bridge_health_label=health_label.replace("_", " "),
    )

    return _persist_and_send(
        db,
        to=patient.caregiver_email,
        subject=rendered.subject,
        body=rendered.body,
        template_key=rendered.template_key,
        caregiver_for_patient_id=patient.id,
    )


# ---------------------------------------------------------------------------
# Emergency alert
# ---------------------------------------------------------------------------


def send_caregiver_emergency_alert(
    db: Session,
    *,
    patient: Patient,
    slot_date,
    tier_label: str,
) -> DispatchOutcome:
    if not patient.caregiver_email:
        return DispatchOutcome(
            sent=False, message_id="", is_mock=True, status="skipped",
            error_message="no caregiver_email",
        )
    rendered = _tmpl.render_caregiver_emergency_alert(
        caregiver_first=(patient.caregiver_name or "there").split()[0],
        patient_name=patient.name or "your patient",
        slot_date=slot_date,
        hospital=patient.hospital or "the hospital",
        tier_label=tier_label,
    )
    return _persist_and_send(
        db,
        to=patient.caregiver_email,
        subject=rendered.subject,
        body=rendered.body,
        template_key=rendered.template_key,
        caregiver_for_patient_id=patient.id,
    )


# ---------------------------------------------------------------------------
# WhatsApp → SES fallback (when Twilio is in mock mode)
# ---------------------------------------------------------------------------


def send_caregiver_whatsapp_fallback(
    db: Session,
    *,
    patient: Patient,
    whatsapp_body: str,
    template_key: str,
) -> DispatchOutcome:
    """Mirror a WhatsApp caregiver message as an email.

    Used by ``send_caregiver_template`` when Twilio is in mock mode — without
    a real WhatsApp send, the caregiver never sees the update. If we have
    their email, we send the same body via SES so the demo / dev environment
    actually reaches a human.
    """
    if not patient.caregiver_email:
        return DispatchOutcome(
            sent=False, message_id="", is_mock=True, status="skipped",
            error_message="no caregiver_email",
        )

    caregiver_first = (
        (patient.caregiver_name or patient.name or "there").split()[0]
        if (patient.caregiver_name or patient.name)
        else "there"
    )
    subject = f"Bridge update for {patient.name or 'your patient'}"
    body = (
        f"Hi {caregiver_first},\n\n"
        "(WhatsApp delivery is unavailable, so we're sending this update via email.)\n\n"
        f"{whatsapp_body}\n\n"
        "— Blood Warriors team"
    )
    return _persist_and_send(
        db,
        to=patient.caregiver_email,
        subject=subject,
        body=body,
        template_key=f"{template_key}__email_fallback",
        caregiver_for_patient_id=patient.id,
    )


# ---------------------------------------------------------------------------
# Coordinator alert
# ---------------------------------------------------------------------------


def send_coordinator_failure_alert(
    db: Session,
    *,
    coordinator_email: str,
    patient_name: str,
    slot_date,
    tier_label: str,
    wave_id: str,
    pings_sent: int,
    pings_accepted: int,
    pings_declined: int,
    pings_no_reply: int,
) -> DispatchOutcome:
    rendered = _tmpl.render_coordinator_failure_alert(
        patient_name=patient_name,
        slot_date=slot_date,
        tier_label=tier_label,
        wave_id=wave_id,
        pings_sent=pings_sent,
        pings_accepted=pings_accepted,
        pings_declined=pings_declined,
        pings_no_reply=pings_no_reply,
    )
    return _persist_and_send(
        db,
        to=coordinator_email,
        subject=rendered.subject,
        body=rendered.body,
        template_key=rendered.template_key,
    )
