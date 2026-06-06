"""Typed publish helpers.

Webhook code calls these rather than the raw SNS client so the message
shapes stay consistent. One helper per topic; each returns the SNS
``MessageId``.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from app.events.topics import TopicName
from app.integrations import sns_client

logger = logging.getLogger(__name__)


def _publish(topic: TopicName, body: dict) -> str:
    res = sns_client.publish(topic.value, body)
    logger.info(
        "published %s (mid=%s, mock=%s) body_keys=%s",
        topic.value, res.message_id, res.is_mock, sorted(body.keys()),
    )
    return res.message_id


def publish_donor_reply_accept(
    *, donor_id: uuid.UUID, ping_id: Optional[uuid.UUID] = None, slot_ref: Optional[str] = None
) -> str:
    return _publish(
        TopicName.DONOR_REPLY_ACCEPT,
        {
            "donor_id": str(donor_id),
            "ping_id": str(ping_id) if ping_id else None,
            "slot_ref": slot_ref,
        },
    )


def publish_donor_reply_decline(
    *, donor_id: uuid.UUID, ping_id: Optional[uuid.UUID] = None, slot_ref: Optional[str] = None,
    reason: Optional[str] = None,
) -> str:
    return _publish(
        TopicName.DONOR_REPLY_DECLINE,
        {
            "donor_id": str(donor_id),
            "ping_id": str(ping_id) if ping_id else None,
            "slot_ref": slot_ref,
            "reason": reason,
        },
    )


def publish_donor_reply_out_of_town(*, donor_id: uuid.UUID) -> str:
    return _publish(
        TopicName.DONOR_REPLY_OUT_OF_TOWN,
        {"donor_id": str(donor_id)},
    )


def publish_donor_reply_medical_defer(
    *, donor_id: uuid.UUID, reason: Optional[str] = None
) -> str:
    return _publish(
        TopicName.DONOR_REPLY_MEDICAL_DEFER,
        {"donor_id": str(donor_id), "reason": reason},
    )


def publish_donor_reply_opt_out(*, donor_id: uuid.UUID) -> str:
    return _publish(
        TopicName.DONOR_REPLY_OPT_OUT,
        {"donor_id": str(donor_id)},
    )


def publish_wave_expired(*, wave_id: uuid.UUID, tier: str) -> str:
    return _publish(
        TopicName.WAVE_EXPIRED,
        {"wave_id": str(wave_id), "tier": tier},
    )


def publish_wave_accepted(
    *, wave_id: uuid.UUID, donor_id: uuid.UUID, slot_date: str
) -> str:
    return _publish(
        TopicName.WAVE_ACCEPTED,
        {
            "wave_id": str(wave_id),
            "donor_id": str(donor_id),
            "slot_date": slot_date,
        },
    )


# ---------------------------------------------------------------------------
# E7 — caregiver email reply publishers
# ---------------------------------------------------------------------------


def publish_caregiver_reply_resolved(
    *, patient_id: uuid.UUID, email_message_id: uuid.UUID, body_excerpt: str
) -> str:
    """Caregiver said 'we're sorted' — subscribers cancel pending outreach
    and notify the coordinator."""
    return _publish(
        TopicName.CAREGIVER_REPLY_RESOLVED,
        {
            "patient_id": str(patient_id),
            "email_message_id": str(email_message_id),
            "body_excerpt": body_excerpt[:300],
        },
    )


def publish_caregiver_reply_urgent(
    *, patient_id: uuid.UUID, email_message_id: uuid.UUID, body_excerpt: str
) -> str:
    """Caregiver flagged the situation as urgent — wake the coordinator."""
    return _publish(
        TopicName.CAREGIVER_REPLY_URGENT,
        {
            "patient_id": str(patient_id),
            "email_message_id": str(email_message_id),
            "body_excerpt": body_excerpt[:300],
        },
    )


def publish_caregiver_reply_question(
    *, patient_id: uuid.UUID, email_message_id: uuid.UUID, body_excerpt: str
) -> str:
    """Generic question — forward to Care Agent for a reply."""
    return _publish(
        TopicName.CAREGIVER_REPLY_QUESTION,
        {
            "patient_id": str(patient_id),
            "email_message_id": str(email_message_id),
            "body_excerpt": body_excerpt[:300],
        },
    )
