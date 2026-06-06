"""G5 — caregiver WhatsApp notifications.

Helpers that fire the *_caregiver templates against `patient.caregiver_phone`,
write a `WhatsAppMessage` row with `patient_id` set + `donor_id` null, and
return a structured result the caller can echo to the UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.integrations import twilio_client
from app.models import (
    Bridge,
    MembershipStatus,
    MessageDirection,
    MessageStatus,
    Patient,
    WhatsAppMessage,
)
from app.services import whatsapp_templates as _tmpl


@dataclass
class CaregiverSendResult:
    skipped_reason: Optional[str]
    message: Optional[WhatsAppMessage]
    template_key: Optional[str]
    language_used: Optional[str]
    fallback_used: bool
    # Phase E2 — set when we also fired an SES email because Twilio was mocked
    email_fallback_message_id: Optional[str] = None
    email_fallback_sent: bool = False


def _active_donor_count(bridge: Optional[Bridge]) -> int:
    if bridge is None:
        return 0
    return sum(
        1
        for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == MembershipStatus.ACTIVE.value
    )


def send_caregiver_template(
    db: Session,
    *,
    patient: Patient,
    template_key: str,
    bridge: Optional[Bridge] = None,
    added_donor_name: str = "",
    language: Optional[str] = None,
    commit: bool = True,
) -> CaregiverSendResult:
    """Render a *_caregiver template and send it via Twilio (or mock).

    No-ops gracefully when the patient has no caregiver_phone configured.
    """
    if not patient.caregiver_phone:
        return CaregiverSendResult(
            skipped_reason="no caregiver_phone configured",
            message=None,
            template_key=template_key,
            language_used=None,
            fallback_used=False,
        )

    chosen_lang = (
        language
        or getattr(patient.preferred_language, "value", str(patient.preferred_language))
        or "en"
    )
    caregiver_first = (
        (patient.caregiver_name or patient.name).split()[0]
        if (patient.caregiver_name or patient.name)
        else "there"
    )
    next_t = ""
    if patient.last_transfusion_date and patient.transfusion_cadence_days:
        from datetime import timedelta as _td
        next_t = (
            patient.last_transfusion_date
            + _td(days=patient.transfusion_cadence_days)
        ).isoformat()

    active_count = _active_donor_count(bridge)
    patient_bg = getattr(patient.blood_group, "value", str(patient.blood_group))

    rendered = _tmpl.render(
        template_key,
        language=chosen_lang,
        donor_first="",
        donor_name="",
        patient_name=patient.name,
        patient_age=patient.age,
        patient_blood_group=patient_bg,
        caregiver_first=caregiver_first,
        added_donor_name=added_donor_name,
        active_donor_count=active_count,
        next_transfusion_date=next_t,
    )

    send_result = twilio_client.send_whatsapp(
        to_number=patient.caregiver_phone, body=rendered.body
    )

    row = WhatsAppMessage(
        donor_id=None,
        bridge_id=bridge.id if bridge else None,
        patient_id=patient.id,
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
        template_key=template_key,
        language=rendered.language_used,
    )
    db.add(row)

    # Phase E2 — SES fallback. When the Twilio send was a mock (so the
    # caregiver never actually received anything) and we have their email,
    # mirror the message via SES so the message lands somewhere a human
    # can see.
    email_fallback_mid: Optional[str] = None
    email_fallback_sent = False
    if send_result.is_mock and patient.caregiver_email:
        try:
            from app.services import email_dispatcher as _email_disp

            outcome = _email_disp.send_caregiver_whatsapp_fallback(
                db,
                patient=patient,
                whatsapp_body=rendered.body,
                template_key=template_key,
            )
            email_fallback_mid = outcome.message_id
            email_fallback_sent = outcome.sent
        except Exception:  # pragma: no cover
            import logging as _log
            _log.getLogger(__name__).exception(
                "SES caregiver fallback failed for patient %s", patient.id
            )

    if commit:
        db.commit()
        db.refresh(row)

    return CaregiverSendResult(
        skipped_reason=None,
        message=row,
        template_key=template_key,
        language_used=rendered.language_used,
        fallback_used=rendered.was_fallback,
        email_fallback_message_id=email_fallback_mid,
        email_fallback_sent=email_fallback_sent,
    )
