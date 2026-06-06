"""G2 — Donor response feedback loop.

Every inbound WhatsApp bumps the donor's rolling `response_rate` and (when we
can compute hours-to-reply) `avg_response_hours` via an EMA with weight α=0.1.
Every outbound that ages past 48h with no reply decays `response_rate`
downward by the same weight — computed lazily on stability reads so we don't
need a periodic task for the demo.

These updates feed directly into the XGBoost features (`response_rate` and
`avg_response_hours` are top-3 predictors), so the next /stability call
literally sees a better-calibrated donor. That's the "model that learns from
every response" line in the pitch becoming true.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from app.agent.memory import record_memory
from app.models import (
    CohortMemory,
    Donor,
    DonorResponseEvent,
    MemoryKind,
    MessageDirection,
    ResponseEventKind,
    WhatsAppMessage,
)


# EMA weight on each new datapoint. 0.1 = each event nudges 10% of the way
# toward the new observation, so 10 events roughly reach the new value.
EMA_ALPHA = 0.1

# Time window we use to look up the outbound an inbound is "replying to".
# Also doubles as the no-reply timeout — outbounds older than this with no
# matching reply trip the decay path.
RESPONSE_WINDOW = timedelta(hours=48)

# When response_rate crosses below this floor (downward), we drop a CohortMemory
# so the agent surfaces the change in its next answer.
LOW_RESPONSE_THRESHOLD = 0.5


@dataclass
class FeedbackResult:
    kind: ResponseEventKind
    prior_response_rate: float
    new_response_rate: float
    prior_avg_hours: Optional[float]
    new_avg_hours: Optional[float]
    hours_to_response: Optional[float]
    crossed_low_threshold: bool


def _ema(old: float, observation: float, alpha: float = EMA_ALPHA) -> float:
    return (1.0 - alpha) * old + alpha * observation


def _most_recent_outbound_within_window(
    db: Session, donor_id: uuid.UUID, before: datetime
) -> Optional[WhatsAppMessage]:
    """The outbound message this inbound is most likely a reply to."""
    cutoff = before - RESPONSE_WINDOW
    return (
        db.execute(
            select(WhatsAppMessage)
            .where(
                WhatsAppMessage.donor_id == donor_id,
                WhatsAppMessage.direction == MessageDirection.OUTBOUND.value,
                WhatsAppMessage.created_at >= cutoff,
                WhatsAppMessage.created_at <= before,
            )
            .order_by(desc(WhatsAppMessage.created_at))
            .limit(1)
        )
        .scalars()
        .first()
    )


def _maybe_record_low_threshold_memory(
    db: Session,
    *,
    donor: Donor,
    prior: float,
    new: float,
    related_template: Optional[str],
) -> bool:
    """If response_rate dropped *across* the threshold downward, write a memory."""
    if prior >= LOW_RESPONSE_THRESHOLD > new:
        tail = f" after no-reply on {related_template}" if related_template else ""
        record_memory(
            db,
            kind=MemoryKind.DONOR,
            entity_id=donor.id,
            summary=(
                f"Donor {donor.name} response rate dropped to {new:.0%}{tail}. "
                f"The stability model will treat them as at-risk on the next "
                f"recommendations refresh."
            ),
        )
        return True
    return False


def apply_inbound_reply(
    db: Session, *, donor: Donor, inbound: WhatsAppMessage, commit: bool = False
) -> FeedbackResult:
    """Donor sent us something. Bump response_rate up + maybe update avg_hours.

    `commit=False` is the default — the caller (webhook) commits at the end so
    the whole turn is one transaction.
    """
    prior_rate = float(donor.response_rate or 0.0)
    prior_hours = float(donor.avg_response_hours) if donor.avg_response_hours else None

    new_rate = _ema(prior_rate, 1.0)

    # Hours-to-response: only when we can pin it to an outbound in the window
    outbound = _most_recent_outbound_within_window(
        db, donor.id, inbound.created_at or datetime.utcnow()
    )
    new_hours: Optional[float] = prior_hours
    hours_to_response: Optional[float] = None
    if outbound is not None:
        gap = (inbound.created_at or datetime.utcnow()) - (
            outbound.created_at or datetime.utcnow()
        )
        hours_to_response = max(0.0, gap.total_seconds() / 3600.0)
        new_hours = (
            _ema(prior_hours, hours_to_response)
            if prior_hours is not None
            else hours_to_response
        )

    # Mutate donor in-place
    donor.response_rate = new_rate
    if new_hours is not None:
        donor.avg_response_hours = new_hours

    event = DonorResponseEvent(
        donor_id=donor.id,
        kind=ResponseEventKind.REPLY,
        message_id=outbound.id if outbound else None,
        hours_to_response=hours_to_response,
        prior_response_rate=prior_rate,
        new_response_rate=new_rate,
        prior_avg_hours=prior_hours,
        new_avg_hours=new_hours,
    )
    db.add(event)
    if commit:
        db.commit()

    return FeedbackResult(
        kind=ResponseEventKind.REPLY,
        prior_response_rate=prior_rate,
        new_response_rate=new_rate,
        prior_avg_hours=prior_hours,
        new_avg_hours=new_hours,
        hours_to_response=hours_to_response,
        crossed_low_threshold=False,  # bumping up never crosses below
    )


def apply_no_reply_decay(
    db: Session,
    *,
    donor: Donor,
    now: Optional[datetime] = None,
    commit: bool = False,
) -> list[FeedbackResult]:
    """Lazy decay: any of this donor's outbounds older than 48h with no scored
    event yet trips a no_reply EMA decay.

    Called from the stability endpoints so the next /stability read reflects
    accurate response_rate without needing a cron job for the demo.
    Returns one FeedbackResult per outbound we just processed (usually 0 or 1).
    """
    now = now or datetime.utcnow()
    cutoff = now - RESPONSE_WINDOW

    # Outbounds to this donor older than the window
    outbound_rows = (
        db.execute(
            select(WhatsAppMessage)
            .where(
                WhatsAppMessage.donor_id == donor.id,
                WhatsAppMessage.direction == MessageDirection.OUTBOUND.value,
                WhatsAppMessage.created_at <= cutoff,
            )
            .order_by(WhatsAppMessage.created_at)
        )
        .scalars()
        .all()
    )
    if not outbound_rows:
        return []

    # Already-scored outbound ids (either a REPLY or a NO_REPLY event exists)
    scored_ids = set(
        db.execute(
            select(DonorResponseEvent.message_id)
            .where(
                DonorResponseEvent.donor_id == donor.id,
                DonorResponseEvent.message_id.in_([o.id for o in outbound_rows]),
            )
        ).scalars()
    )
    pending = [o for o in outbound_rows if o.id not in scored_ids]
    if not pending:
        return []

    results: list[FeedbackResult] = []
    for outbound in pending:
        prior_rate = float(donor.response_rate or 0.0)
        new_rate = _ema(prior_rate, 0.0)
        donor.response_rate = new_rate

        event = DonorResponseEvent(
            donor_id=donor.id,
            kind=ResponseEventKind.NO_REPLY,
            message_id=outbound.id,
            hours_to_response=None,
            prior_response_rate=prior_rate,
            new_response_rate=new_rate,
            prior_avg_hours=donor.avg_response_hours,
            new_avg_hours=donor.avg_response_hours,
        )
        db.add(event)

        crossed = _maybe_record_low_threshold_memory(
            db,
            donor=donor,
            prior=prior_rate,
            new=new_rate,
            related_template=outbound.template_key,
        )
        results.append(
            FeedbackResult(
                kind=ResponseEventKind.NO_REPLY,
                prior_response_rate=prior_rate,
                new_response_rate=new_rate,
                prior_avg_hours=donor.avg_response_hours,
                new_avg_hours=donor.avg_response_hours,
                hours_to_response=None,
                crossed_low_threshold=crossed,
            )
        )

    if commit:
        db.commit()
    return results


def apply_no_reply_decay_for_bridge(
    db: Session, donors: list[Donor], now: Optional[datetime] = None
) -> dict[uuid.UUID, int]:
    """Convenience: run lazy decay for every donor in a cohort. Returns count
    of decay events per donor (mostly 0)."""
    counts: dict[uuid.UUID, int] = {}
    for d in donors:
        results = apply_no_reply_decay(db, donor=d, now=now)
        if results:
            counts[d.id] = len(results)
    return counts


def response_history(
    db: Session, donor_id: uuid.UUID, *, days: int = 30
) -> list[DonorResponseEvent]:
    """Events newer than `days` ago, oldest first (sparkline draw order)."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    return list(
        db.execute(
            select(DonorResponseEvent)
            .where(
                DonorResponseEvent.donor_id == donor_id,
                DonorResponseEvent.created_at >= cutoff,
            )
            .order_by(DonorResponseEvent.created_at)
        ).scalars()
    )
