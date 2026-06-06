"""On wave expiry, re-trigger the allocator for the affected slot.

The expire_and_escalate scheduler job already creates the next-tier wave —
this subscriber is the audit trail that we DID receive the wave.expired
event. Once we deploy and the SNS topic gets a Lambda subscriber, this is
where horizontal scale starts.
"""

from __future__ import annotations

import logging

from app.events.dispatcher import register_subscriber
from app.events.topics import TopicName

logger = logging.getLogger(__name__)


@register_subscriber(TopicName.WAVE_EXPIRED, name="allocator_refire_audit")
def on_wave_expired(body: dict, session_factory) -> None:
    wid = body.get("wave_id")
    tier = body.get("tier")
    logger.info(
        "allocator_refire_audit: wave %s expired at tier %s (auto-escalation runs from scheduler)",
        wid, tier,
    )
