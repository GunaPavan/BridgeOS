"""Cooldown subscribers.

The classifier side-effect path (Phase C) already sets cooldowns inline.
These subscribers act as an additional defence-in-depth layer + the audit
trail for the event bus. They are idempotent — duplicate published events
won't double-cool a donor (we check for an existing cooldown).

In production this work will move into a Lambda that subscribes to the SNS
topic via SQS — at which point the in-process subscriber stays disabled
in prod (via env var) but remains the dev/test fallback.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import and_, select

from app.events.dispatcher import register_subscriber
from app.events.topics import TopicName

logger = logging.getLogger(__name__)


def _set_cooldown_if_absent(
    db, donor_id: uuid.UUID, reason, days: int, notes: str
) -> bool:
    """Insert a cooldown row only if one with the same reason isn't already
    active. Returns True if a new row was added."""
    from app.models import OutreachCooldown

    now = datetime.utcnow()
    existing = db.execute(
        select(OutreachCooldown).where(
            and_(
                OutreachCooldown.donor_id == donor_id,
                OutreachCooldown.reason == reason,
                OutreachCooldown.expires_at > now,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    db.add(
        OutreachCooldown(
            donor_id=donor_id,
            patient_id=None,
            reason=reason,
            expires_at=now + timedelta(days=days),
            notes=notes,
        )
    )
    return True


@register_subscriber(TopicName.DONOR_REPLY_OUT_OF_TOWN, name="cooldown_out_of_town_audit")
def on_out_of_town(body: dict, session_factory) -> None:
    """Belt-and-suspenders 7-day cooldown."""
    from app.models import CooldownReason

    did = body.get("donor_id")
    if not did:
        return
    with session_factory() as db:
        try:
            _set_cooldown_if_absent(
                db, uuid.UUID(did), CooldownReason.OPT_OUT_TEMPORARY, days=7,
                notes="event-bus: out_of_town audit cooldown",
            )
            db.commit()
        except Exception:
            logger.exception("cooldown_out_of_town_audit failed for donor %s", did)


@register_subscriber(TopicName.DONOR_REPLY_MEDICAL_DEFER, name="cooldown_medical_audit")
def on_medical(body: dict, session_factory) -> None:
    from app.models import CooldownReason

    did = body.get("donor_id")
    reason = body.get("reason")
    if not did:
        return
    with session_factory() as db:
        try:
            _set_cooldown_if_absent(
                db, uuid.UUID(did), CooldownReason.OPT_OUT_TEMPORARY, days=14,
                notes=f"event-bus: medical_defer audit cooldown — {reason or ''}",
            )
            db.commit()
        except Exception:
            logger.exception("cooldown_medical_audit failed for donor %s", did)


@register_subscriber(TopicName.DONOR_REPLY_OPT_OUT, name="cooldown_opt_out_audit")
def on_opt_out(body: dict, session_factory) -> None:
    from app.models import CooldownReason

    did = body.get("donor_id")
    if not did:
        return
    with session_factory() as db:
        try:
            _set_cooldown_if_absent(
                db, uuid.UUID(did), CooldownReason.OPT_OUT_TEMPORARY, days=365,
                notes="event-bus: opt_out audit cooldown",
            )
            db.commit()
        except Exception:
            logger.exception("cooldown_opt_out_audit failed for donor %s", did)
