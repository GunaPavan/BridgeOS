"""On wave acceptance, mark sibling PENDING pings as CANCELLED so we don't
keep bothering donors whose slot is now covered."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import and_, select

from app.events.dispatcher import register_subscriber
from app.events.topics import TopicName

logger = logging.getLogger(__name__)


@register_subscriber(TopicName.WAVE_ACCEPTED, name="sibling_cancel_audit")
def on_wave_accepted(body: dict, session_factory) -> None:
    from app.models import OutreachPing, PingResponse

    wave_id = body.get("wave_id")
    if not wave_id:
        return
    with session_factory() as db:
        try:
            wid = uuid.UUID(wave_id)
            pending = db.execute(
                select(OutreachPing).where(
                    and_(
                        OutreachPing.wave_id == wid,
                        OutreachPing.response == PingResponse.PENDING,
                    )
                )
            ).scalars().all()
            now = datetime.utcnow()
            for p in pending:
                p.response = PingResponse.CANCELLED
                p.response_at = now
            db.commit()
            logger.info("sibling_cancel: cancelled %d pings on wave %s", len(pending), wid)
        except Exception:
            logger.exception("sibling_cancel failed for wave %s", wave_id)
