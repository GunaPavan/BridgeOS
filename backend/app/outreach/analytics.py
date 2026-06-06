"""Phase F — outreach analytics.

Surfaces operational metrics for the allocator + emergency events.
Used by the /analytics/outreach panel.

Key signals:
    pings_per_acceptance      — efficiency (1.0 = every ping converts; 5.0 = need 5
                                pings per yes)
    avg_minutes_to_accept     — speed by tier
    donor_fatigue_distribution — pings_last_30_days bucketed
    waves_by_tier             — count + outcome breakdown
    emergency_events_recent   — last N triggers with status
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import (
    Donor,
    EmergencyEvent,
    EmergencyEventStatus,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    PingResponse,
)


@dataclass(frozen=True)
class OutreachAnalytics:
    waves_total: int
    waves_active: int
    waves_accepted: int
    waves_expired: int
    waves_by_tier: dict[str, int]
    pings_total: int
    pings_accepted: int
    pings_declined: int
    pings_no_reply: int
    pings_pending: int
    pings_per_acceptance: float
    avg_minutes_to_accept_by_urgency: dict[str, float]
    donor_fatigue_distribution: dict[str, int]
    emergency_events_total: int
    emergency_events_active: int
    emergency_events_recent: list[dict]


def compute_outreach_analytics(
    db: Session, *, lookback_days: int = 30, recent_events: int = 5
) -> OutreachAnalytics:
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    # ----- waves -----
    waves = (
        db.execute(select(OutreachWave).where(OutreachWave.created_at >= cutoff))
        .scalars()
        .all()
    )
    waves_total = len(waves)
    waves_active = sum(1 for w in waves if w.status == OutreachWaveStatus.ACTIVE)
    waves_accepted = sum(1 for w in waves if w.status == OutreachWaveStatus.ACCEPTED)
    waves_expired = sum(1 for w in waves if w.status == OutreachWaveStatus.EXPIRED)
    waves_by_tier: dict[str, int] = {}
    for w in waves:
        k = getattr(w.tier, "value", str(w.tier))
        waves_by_tier[k] = waves_by_tier.get(k, 0) + 1

    # ----- pings -----
    pings = (
        db.execute(select(OutreachPing).where(OutreachPing.sent_at >= cutoff))
        .scalars()
        .all()
    )
    pings_total = len(pings)
    pings_accepted = sum(1 for p in pings if p.response == PingResponse.ACCEPTED)
    pings_declined = sum(1 for p in pings if p.response == PingResponse.DECLINED)
    pings_no_reply = sum(1 for p in pings if p.response == PingResponse.NO_REPLY)
    pings_pending = sum(1 for p in pings if p.response == PingResponse.PENDING)
    pings_per_acceptance = (
        pings_total / pings_accepted if pings_accepted > 0 else float(pings_total or 0)
    )

    # ----- avg time-to-accept (by urgency) -----
    avg_by_urgency: dict[str, list[float]] = {}
    for p in pings:
        if p.response != PingResponse.ACCEPTED or p.response_at is None:
            continue
        wave = next((w for w in waves if w.id == p.wave_id), None)
        if wave is None:
            continue
        minutes = (p.response_at - p.sent_at).total_seconds() / 60.0
        k = getattr(wave.urgency, "value", str(wave.urgency))
        avg_by_urgency.setdefault(k, []).append(minutes)
    avg_minutes_to_accept_by_urgency = {
        k: round(sum(v) / len(v), 1) if v else 0.0
        for k, v in avg_by_urgency.items()
    }

    # ----- donor fatigue distribution -----
    # Bucket donors by how many pings they got in the last 30 days
    fatigue_stmt = (
        select(OutreachPing.donor_id, func.count(OutreachPing.id))
        .where(OutreachPing.sent_at >= cutoff)
        .group_by(OutreachPing.donor_id)
    )
    rows = db.execute(fatigue_stmt).all()
    buckets = {"0": 0, "1": 0, "2": 0, "3-5": 0, "6+": 0}
    pinged_donor_ids: set = set()
    for donor_id, count in rows:
        pinged_donor_ids.add(donor_id)
        if count == 1:
            buckets["1"] += 1
        elif count == 2:
            buckets["2"] += 1
        elif 3 <= count <= 5:
            buckets["3-5"] += 1
        else:
            buckets["6+"] += 1
    # "0" bucket = active donors who got NO pings in the window — the healthy resting group
    total_active = (
        db.execute(select(func.count(Donor.id)).where(Donor.is_active.is_(True))).scalar_one() or 0
    )
    buckets["0"] = max(0, total_active - sum(v for k, v in buckets.items() if k != "0"))

    # ----- emergency events -----
    emergencies = (
        db.execute(
            select(EmergencyEvent)
            .where(EmergencyEvent.triggered_at >= cutoff)
            .order_by(EmergencyEvent.triggered_at.desc())
        )
        .scalars()
        .all()
    )
    em_total = len(emergencies)
    em_active = sum(
        1 for e in emergencies if e.status == EmergencyEventStatus.ACTIVE
    )
    em_recent = [
        {
            "id": str(e.id),
            "patient_id": str(e.patient_id),
            "triggered_at": e.triggered_at.isoformat() + "Z" if e.triggered_at else None,
            "triggered_by": e.triggered_by,
            "hospital_name": e.hospital_name,
            "reach_window_min": e.reach_window_min,
            "pool_size_at_trigger": e.pool_size_at_trigger,
            "status": getattr(e.status, "value", str(e.status)),
        }
        for e in emergencies[:recent_events]
    ]

    return OutreachAnalytics(
        waves_total=waves_total,
        waves_active=waves_active,
        waves_accepted=waves_accepted,
        waves_expired=waves_expired,
        waves_by_tier=waves_by_tier,
        pings_total=pings_total,
        pings_accepted=pings_accepted,
        pings_declined=pings_declined,
        pings_no_reply=pings_no_reply,
        pings_pending=pings_pending,
        pings_per_acceptance=round(pings_per_acceptance, 2),
        avg_minutes_to_accept_by_urgency=avg_minutes_to_accept_by_urgency,
        donor_fatigue_distribution=buckets,
        emergency_events_total=em_total,
        emergency_events_active=em_active,
        emergency_events_recent=em_recent,
    )
