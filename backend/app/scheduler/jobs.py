"""Job handlers.

Each function is a pure ``(db: Session, now: datetime) -> JobResult`` callable.
Phase A wires only ``auto_run_cycle`` + ``auto_expire_and_escalate`` to real
implementations — Phase B fills in the follow-up jobs. Until then the
follow-up handlers return a SKIPPED result so they don't crash the scheduler
when registered.

KEEPING THIS PURE matters:
  • Tests can inject any db + frozen ``now`` and assert on JobResult.
  • The same functions run unchanged when we swap APScheduler for
    EventBridge Scheduler + Lambda (Lambda hands you a fresh session
    per invocation; everything else is identical).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.scheduler.metrics import JobResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase A — allocator + expiry
# ---------------------------------------------------------------------------


def auto_run_cycle(db: Session, now: datetime) -> JobResult:
    """Run one allocator cycle, commit waves, dispatch via WhatsApp.

    Returns counts of waves created + pings planned in ``payload`` so the
    UI can show "Last allocator run: 4 waves / 11 pings, 2 critical".
    """
    from app.outreach.engine import run_cycle

    today = now.date()
    summary, allocations = run_cycle(db, today=today, dry_run=False)

    return JobResult(
        items_processed=summary.waves_created,
        payload={
            "open_slots": summary.open_slots,
            "waves_created": summary.waves_created,
            "pings_planned": summary.pings_planned,
            "critical_slots": summary.critical_slots,
            "high_slots": summary.high_slots,
            "medium_slots": summary.medium_slots,
            "fully_covered_slots": summary.fully_covered_slots,
            "shortfall_slots": summary.shortfall_slots,
        },
    )


def auto_expire_and_escalate(db: Session, now: datetime) -> JobResult:
    """Mark past-due waves EXPIRED then escalate each to its next tier."""
    from app.outreach.engine import (
        escalate_wave_to_next_tier,
        expire_and_escalate_waves,
    )

    expired = expire_and_escalate_waves(db, now=now)

    today: date = now.date()
    escalated: list[dict[str, Any]] = []
    for wave in expired:
        new_wave = escalate_wave_to_next_tier(
            db, expired_wave=wave, today=today, now=now
        )
        if new_wave is not None:
            escalated.append(
                {
                    "expired_wave_id": str(wave.id),
                    "new_wave_id": str(new_wave.id),
                    "new_tier": getattr(new_wave.tier, "value", str(new_wave.tier)),
                }
            )
    db.commit()

    return JobResult(
        items_processed=len(expired),
        payload={
            "expired_count": len(expired),
            "escalated_count": len(escalated),
            "escalations": escalated[:20],  # cap so the audit row stays small
        },
    )


# ---------------------------------------------------------------------------
# Phase B — automated follow-ups
# ---------------------------------------------------------------------------


def _is_quiet_hours_now(now: datetime) -> bool:
    """Local import so the scheduler module stays cheap to load."""
    from app.outreach.dispatch import is_quiet_hours

    return is_quiet_hours(now)


def auto_pending_nudge(db: Session, now: datetime) -> JobResult:
    """Nudge donors whose pings are still PENDING past the configured threshold.

    Eligibility filter:
      - ``response = PENDING``
      - ``sent_at < now - NUDGE_PENDING_AFTER_HOURS``
      - ``last_nudge_at IS NULL`` OR ``last_nudge_at < now - NUDGE_MIN_GAP_HOURS``
      - ``nudge_count < NUDGE_MAX_PER_PING``

    Skipped during quiet hours — the next non-quiet tick picks them up.
    """
    from sqlalchemy import and_, or_, select

    from app.models import OutreachPing, PingResponse
    from app.outreach.followups import (
        NUDGE_MAX_PER_PING,
        NUDGE_MIN_GAP_HOURS,
        NUDGE_PENDING_AFTER_HOURS,
        send_pending_nudge,
    )

    if _is_quiet_hours_now(now):
        return JobResult(
            items_processed=0,
            skipped_reason="quiet_hours",
        )

    sent_cutoff = now - timedelta(hours=NUDGE_PENDING_AFTER_HOURS)
    nudge_cutoff = now - timedelta(hours=NUDGE_MIN_GAP_HOURS)

    stmt = select(OutreachPing).where(
        and_(
            OutreachPing.response == PingResponse.PENDING,
            OutreachPing.sent_at <= sent_cutoff,
            OutreachPing.nudge_count < NUDGE_MAX_PER_PING,
            or_(
                OutreachPing.last_nudge_at.is_(None),
                OutreachPing.last_nudge_at <= nudge_cutoff,
            ),
        )
    )
    pings = db.execute(stmt).scalars().all()

    sent = 0
    failed = 0
    for ping in pings:
        if send_pending_nudge(db, ping=ping, now=now):
            sent += 1
        else:
            failed += 1
    db.commit()

    return JobResult(
        items_processed=sent,
        payload={"candidates": len(pings), "sent": sent, "failed": failed},
    )


def auto_pre_donation_reminder(db: Session, now: datetime) -> JobResult:
    """Day-before commitment reminder for ACCEPTED pings whose slot is
    tomorrow and have NOT been reminded yet.

    Skipped during quiet hours.
    """
    from sqlalchemy import and_, select

    from app.models import OutreachPing, OutreachWave, PingResponse
    from app.outreach.followups import send_pre_donation_reminder

    if _is_quiet_hours_now(now):
        return JobResult(
            items_processed=0,
            skipped_reason="quiet_hours",
        )

    tomorrow = (now + timedelta(days=1)).date()
    stmt = (
        select(OutreachPing)
        .join(OutreachWave, OutreachPing.wave_id == OutreachWave.id)
        .where(
            and_(
                OutreachPing.response == PingResponse.ACCEPTED,
                OutreachWave.slot_date == tomorrow,
                OutreachPing.reminder_sent_at.is_(None),
            )
        )
    )
    pings = db.execute(stmt).scalars().all()

    sent = 0
    failed = 0
    for ping in pings:
        if send_pre_donation_reminder(db, ping=ping, now=now):
            sent += 1
        else:
            failed += 1
    db.commit()

    return JobResult(
        items_processed=sent,
        payload={"candidates": len(pings), "sent": sent, "failed": failed},
    )


def auto_caregiver_email_digest(db: Session, now: datetime) -> JobResult:
    """Daily SES digest to every patient's caregiver who has an email.

    Skipped:
      - Patients without a caregiver_email
      - Inactive patients
    Otherwise: one ``send_caregiver_daily_digest`` per qualifying patient.
    """
    from sqlalchemy import select

    from app.models import Patient
    from app.services.email_dispatcher import send_caregiver_daily_digest

    stmt = select(Patient).where(
        Patient.active.is_(True), Patient.caregiver_email.is_not(None)
    )
    patients = db.execute(stmt).scalars().all()

    sent = 0
    failed = 0
    skipped = 0
    for p in patients:
        outcome = send_caregiver_daily_digest(db, patient=p)
        if outcome.sent:
            sent += 1
        elif outcome.status == "skipped":
            skipped += 1
        else:
            failed += 1
    db.commit()

    return JobResult(
        items_processed=sent,
        payload={
            "patients_total": len(patients),
            "sent": sent,
            "skipped": skipped,
            "failed": failed,
        },
    )


def auto_post_donation_thank_you(db: Session, now: datetime) -> JobResult:
    """Thank-you for ACCEPTED pings whose slot was yesterday (donation should
    have happened) and have NOT been thanked yet.

    Skipped during quiet hours.
    """
    from sqlalchemy import and_, select

    from app.models import OutreachPing, OutreachWave, PingResponse
    from app.outreach.followups import send_post_donation_thank_you

    if _is_quiet_hours_now(now):
        return JobResult(
            items_processed=0,
            skipped_reason="quiet_hours",
        )

    cutoff_date = now.date() - timedelta(days=1)
    stmt = (
        select(OutreachPing)
        .join(OutreachWave, OutreachPing.wave_id == OutreachWave.id)
        .where(
            and_(
                OutreachPing.response == PingResponse.ACCEPTED,
                OutreachWave.slot_date <= cutoff_date,
                OutreachPing.thank_you_sent_at.is_(None),
            )
        )
    )
    pings = db.execute(stmt).scalars().all()

    sent = 0
    failed = 0
    for ping in pings:
        if send_post_donation_thank_you(db, ping=ping, now=now):
            sent += 1
        else:
            failed += 1
    db.commit()

    return JobResult(
        items_processed=sent,
        payload={"candidates": len(pings), "sent": sent, "failed": failed},
    )
