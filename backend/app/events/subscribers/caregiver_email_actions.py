"""E7 — caregiver email reply subscribers.

When a caregiver replies to a digest email and the classifier maps it to
one of the caregiver-reply-* topics, these subscribers run side effects:

  caregiver-reply-resolved → cancel all PENDING outreach pings + active
                             waves for the patient (the caregiver said
                             "we're sorted, stop reaching out")
  caregiver-reply-urgent   → write an audit row + (post-deploy) page the
                             coordinator. Today we log a high-severity
                             warning so the operator sees it in the feed.
  caregiver-reply-question → log + (post-deploy) auto-reply via Care Agent

All subscribers must be idempotent — SNS doesn't guarantee exactly-once.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from app.events.dispatcher import register_subscriber
from app.events.topics import TopicName

logger = logging.getLogger(__name__)


@register_subscriber(TopicName.CAREGIVER_REPLY_RESOLVED, name="caregiver_resolved_cancel_outreach")
def cancel_outreach_when_caregiver_resolved(body: dict, session_factory) -> None:
    """Cancel all PENDING outreach pings + ACTIVE waves for the patient."""
    from app.models import (
        OutreachPing,
        OutreachWave,
        OutreachWaveStatus,
        PingResponse,
    )

    patient_id_raw = body.get("patient_id")
    if not patient_id_raw:
        logger.warning("caregiver_resolved: missing patient_id in body")
        return
    try:
        patient_id = uuid.UUID(patient_id_raw)
    except Exception:
        logger.warning("caregiver_resolved: bad patient_id %r", patient_id_raw)
        return

    with session_factory() as session:
        # Cancel ACTIVE waves
        active_waves = (
            session.query(OutreachWave)
            .filter(
                OutreachWave.patient_id == patient_id,
                OutreachWave.status == OutreachWaveStatus.ACTIVE,
            )
            .all()
        )
        cancelled_waves = 0
        cancelled_pings = 0
        for w in active_waves:
            w.status = OutreachWaveStatus.EXPIRED
            cancelled_waves += 1
            for p in w.pings:
                if p.response == PingResponse.PENDING:
                    p.response = PingResponse.CANCELLED
                    p.response_at = datetime.utcnow()
                    cancelled_pings += 1
        session.commit()
        logger.info(
            "caregiver_resolved: patient=%s cancelled %d waves / %d pings",
            patient_id, cancelled_waves, cancelled_pings,
        )


@register_subscriber(TopicName.CAREGIVER_REPLY_URGENT, name="caregiver_urgent_audit")
def log_urgent_caregiver_reply(body: dict, session_factory) -> None:
    """High-severity log so it shows up in the operator feed.

    Post-deploy this would page the coordinator (SES → SMS via Twilio,
    or Slack webhook, or push notification)."""
    patient_id = body.get("patient_id")
    excerpt = body.get("body_excerpt", "")
    logger.warning(
        "URGENT caregiver reply for patient=%s: %r", patient_id, excerpt[:200]
    )


@register_subscriber(TopicName.CAREGIVER_REPLY_QUESTION, name="caregiver_question_log")
def log_caregiver_question(body: dict, session_factory) -> None:
    """Audit log only for now — post-deploy this routes to Care Agent for
    an automated reply."""
    patient_id = body.get("patient_id")
    excerpt = body.get("body_excerpt", "")
    logger.info(
        "Caregiver question for patient=%s: %r", patient_id, excerpt[:200]
    )
