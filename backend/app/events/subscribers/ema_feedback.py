"""EMA feedback subscriber — bumps donor.response_rate on every reply."""

from __future__ import annotations

import logging
import uuid

from app.events.dispatcher import register_subscriber
from app.events.topics import TopicName

logger = logging.getLogger(__name__)


def _bump(body: dict, session_factory) -> None:
    from app.models import Donor

    did = body.get("donor_id")
    if not did:
        return
    with session_factory() as db:
        try:
            donor = db.get(Donor, uuid.UUID(did))
            if donor is None:
                return
            # Lightweight EMA bump: bias response_rate upward by 5% of the gap.
            # The full G2 feedback loop runs from the webhook directly; this is
            # the audit-trail subscriber.
            current = donor.response_rate or 0.0
            donor.response_rate = round(min(1.0, current + 0.05 * (1.0 - current)), 4)
            db.commit()
        except Exception:
            logger.exception("ema_feedback subscriber failed for donor %s", did)


@register_subscriber(TopicName.DONOR_REPLY_ACCEPT, name="ema_feedback_audit")
def on_accept(body: dict, session_factory) -> None:
    _bump(body, session_factory)


@register_subscriber(TopicName.DONOR_REPLY_DECLINE, name="ema_feedback_audit")
def on_decline(body: dict, session_factory) -> None:
    _bump(body, session_factory)
