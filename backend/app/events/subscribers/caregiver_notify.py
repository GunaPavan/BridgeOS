"""Caregiver notification on donor accept.

When a donor accepts an outreach wave, the caregiver should know. Today
the side-effect handler did this inline in the webhook; we move it here
so the webhook returns fast and additional subscribers can be added
without re-touching webhook code.
"""

from __future__ import annotations

import logging
import uuid

from app.events.dispatcher import register_subscriber
from app.events.topics import TopicName

logger = logging.getLogger(__name__)


@register_subscriber(TopicName.DONOR_REPLY_ACCEPT, name="caregiver_notify")
def on_accept(body: dict, session_factory) -> None:
    """Resolve the patient + caregiver, send a WhatsApp + Email ack."""
    from app.models import OutreachPing, Patient

    ping_id = body.get("ping_id")
    if not ping_id:
        return

    with session_factory() as db:
        try:
            ping = db.get(OutreachPing, uuid.UUID(ping_id))
        except Exception:
            return
        if ping is None or ping.wave is None:
            return
        patient = db.get(Patient, ping.wave.patient_id)
        if patient is None:
            return

        # Try WhatsApp first (existing caregiver flow)
        try:
            from app.services.caregiver_notifications import notify_caregiver_bridge_covered  # type: ignore[attr-defined]

            notify_caregiver_bridge_covered(db=db, patient=patient, ping=ping)
        except Exception:
            logger.exception("caregiver WhatsApp notify failed for ping %s", ping_id)

        # Email fallback if caregiver has an email address
        if patient.caregiver_email:
            try:
                from app.services.email_dispatcher import send_caregiver_emergency_alert
                # This is the "good news" version — we reuse the emergency
                # template to share that the slot is covered. Phase F can
                # add a dedicated `caregiver_bridge_covered_email` template.
                send_caregiver_emergency_alert(
                    db,
                    patient=patient,
                    slot_date=ping.wave.slot_date,
                    tier_label="Tier 1 — slot covered",
                )
            except Exception:
                logger.exception("caregiver email notify failed for ping %s", ping_id)
        db.commit()
