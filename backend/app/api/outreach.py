"""Outreach API — the allocator's surface.

Endpoints:
    POST /outreach/run-cycle?dry_run=true   — run the global allocator
    GET  /outreach/waves                    — list active/recent waves
    GET  /outreach/waves/{wave_id}          — wave detail with pings
    POST /outreach/expire-and-sweep         — manually expire stale waves

Phase B exposes the allocator's *decision*; Phase C wires the actual
WhatsApp dispatch + acceptance close.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import OutreachPing, OutreachWave, OutreachWaveStatus
from app import system_clock
from app.outreach.dispatch import (
    DispatchSummary,
    cancel_outreach_acceptance,
    confirm_outreach_acceptance,
    dispatch_wave,
    expire_pending_pings,
    record_outreach_decline,
)
from app.outreach.engine import (
    CycleSummary,
    escalate_wave_to_next_tier,
    expire_and_escalate_waves,
    run_cycle,
)
from app.outreach.analytics import compute_outreach_analytics
from app.outreach.emergency import (
    EmergencyTriggerResult,
    get_emergency_event,
    trigger_emergency,
)
from app.models import (
    EmergencyEvent,
    EmergencyEventStatus,
)
from pydantic import BaseModel, Field

router = APIRouter(prefix="/outreach", tags=["outreach"])


# ---------- POST /outreach/run-cycle ----------


@router.post(
    "/run-cycle",
    summary="Run the global donor-outreach allocator for one cycle",
)
def post_run_cycle(
    dry_run: bool = Query(False, description="Preview only — don't persist waves"),
    horizon_days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
) -> dict:
    """Run the allocator once.

    Collects every open slot inside the horizon, scores per-patient candidate
    pools, runs the greedy global solver under per-donor concurrency cap of 1,
    and (unless ``dry_run``) materialises ``OutreachWave`` + ``OutreachPing``
    rows ready for Phase C dispatch.

    Returns a summary plus the proposed allocations — useful for the
    coordinator preview UX (the /recommendations dashboard can show "the
    allocator wants to ping these 14 donors across 5 patients").
    """
    summary, allocations = run_cycle(
        db, today=system_clock.today(), horizon_days=horizon_days, dry_run=dry_run
    )
    return {
        "summary": _summary_to_dict(summary),
        "allocations": [
            {
                "patient_id": str(a.slot.patient.id),
                "patient_name": a.slot.patient.name,
                "slot_date": a.slot.slot_date.isoformat(),
                "urgency": a.slot.urgency.tier.value,
                "gap_days": a.slot.urgency.gap_days,
                "target_p_accept": a.target_p_accept,
                "realised_p_accept": round(a.realised_p_accept, 4),
                "fully_covered": a.fully_covered,
                "pool_size": len(a.scored),
                "batch_size": len(a.donors),
                "batch": [
                    {
                        "donor_id": str(d.id),
                        "donor_name": d.name,
                        "blood_group": getattr(
                            d.blood_group, "value", str(d.blood_group)
                        ),
                        "city": d.city,
                        "preferred_language": getattr(
                            d.preferred_language, "value", str(d.preferred_language)
                        ),
                    }
                    for d in a.donors
                ],
            }
            for a in allocations
        ],
    }


def _summary_to_dict(s: CycleSummary) -> dict:
    return {
        "cycle_at": s.cycle_at.isoformat() + "Z",
        "open_slots": s.open_slots,
        "waves_created": s.waves_created,
        "pings_planned": s.pings_planned,
        "critical_slots": s.critical_slots,
        "high_slots": s.high_slots,
        "medium_slots": s.medium_slots,
        "fully_covered_slots": s.fully_covered_slots,
        "shortfall_slots": s.shortfall_slots,
        "dry_run": s.dry_run,
    }


# ---------- GET /outreach/waves ----------


@router.get("/waves", summary="List recent outreach waves")
def list_waves(
    status: Optional[str] = Query(
        None, description="Filter by status: active|accepted|expired|cancelled"
    ),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(OutreachWave).order_by(desc(OutreachWave.created_at)).limit(limit)
    if status:
        stmt = stmt.where(OutreachWave.status == status)
    waves = db.execute(stmt).scalars().all()
    return {
        "items": [_wave_to_summary(w) for w in waves],
        "total": len(waves),
    }


@router.get(
    "/waves/{wave_id}",
    summary="One wave with its pings",
)
def get_wave(wave_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    stmt = (
        select(OutreachWave)
        .options(joinedload(OutreachWave.pings))
        .where(OutreachWave.id == wave_id)
    )
    wave = db.execute(stmt).unique().scalar_one_or_none()
    if wave is None:
        raise HTTPException(status_code=404, detail=f"Wave {wave_id} not found")
    return {
        **_wave_to_summary(wave),
        "pings": [
            {
                "id": str(p.id),
                "donor_id": str(p.donor_id),
                "channel": getattr(p.channel, "value", str(p.channel)),
                "response": getattr(p.response, "value", str(p.response)),
                "sent_at": p.sent_at.isoformat() + "Z" if p.sent_at else None,
                "expires_at": p.expires_at.isoformat() + "Z" if p.expires_at else None,
                "response_at": p.response_at.isoformat() + "Z" if p.response_at else None,
                "composite_score": p.composite_score,
                "adjusted_response_rate": p.adjusted_response_rate,
                "language": p.language,
            }
            for p in wave.pings
        ],
    }


def _wave_to_summary(w: OutreachWave) -> dict:
    return {
        "id": str(w.id),
        "patient_id": str(w.patient_id),
        "bridge_id": str(w.bridge_id) if w.bridge_id else None,
        "slot_date": w.slot_date.isoformat(),
        "tier": getattr(w.tier, "value", str(w.tier)),
        "urgency": getattr(w.urgency, "value", str(w.urgency)),
        "status": getattr(w.status, "value", str(w.status)),
        "target_p_accept": w.target_p_accept,
        "realised_p_accept": w.realised_p_accept,
        "gap_days_at_creation": w.gap_days_at_creation,
        "pool_size_at_creation": w.pool_size_at_creation,
        "triggered_by": w.triggered_by,
        "created_at": w.created_at.isoformat() + "Z" if w.created_at else None,
        "expires_at": w.expires_at.isoformat() + "Z" if w.expires_at else None,
        "resolved_at": w.resolved_at.isoformat() + "Z" if w.resolved_at else None,
        "resolved_by_donor_id": (
            str(w.resolved_by_donor_id) if w.resolved_by_donor_id else None
        ),
    }


# ---------- POST /outreach/expire-and-sweep ----------


@router.get(
    "/analytics",
    summary="Outreach allocator analytics — pings-per-acceptance, fatigue, emergencies",
)
def get_outreach_analytics(
    lookback_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> dict:
    """Operational metrics over the last ``lookback_days``.

    Used by the /analytics page's outreach panel. Lookback default is 30 days
    which matches the typical Blood Warriors monthly review cadence.
    """
    a = compute_outreach_analytics(db, lookback_days=lookback_days)
    return {
        "lookback_days": lookback_days,
        "waves": {
            "total": a.waves_total,
            "active": a.waves_active,
            "accepted": a.waves_accepted,
            "expired": a.waves_expired,
            "by_tier": a.waves_by_tier,
        },
        "pings": {
            "total": a.pings_total,
            "accepted": a.pings_accepted,
            "declined": a.pings_declined,
            "no_reply": a.pings_no_reply,
            "pending": a.pings_pending,
            "pings_per_acceptance": a.pings_per_acceptance,
            "avg_minutes_to_accept_by_urgency": a.avg_minutes_to_accept_by_urgency,
        },
        "donor_fatigue": a.donor_fatigue_distribution,
        "emergency": {
            "total": a.emergency_events_total,
            "active": a.emergency_events_active,
            "recent": a.emergency_events_recent,
        },
    }


@router.post(
    "/expire-and-sweep",
    summary="Expire stale waves AND auto-create the next-tier wave per slot",
)
def post_expire_and_sweep(
    auto_escalate: bool = Query(
        True,
        description=(
            "If true (default), every expired wave automatically spawns the "
            "next-tier wave (Tier 1 -> Tier 2 -> Tier 3 -> external). Disable "
            "to expire only, leaving escalation manual."
        ),
    ),
    db: Session = Depends(get_db),
) -> dict:
    expired = expire_and_escalate_waves(db)
    # For each expired wave, NO_REPLY the still-PENDING pings + cooldown
    escalations: list[str] = []
    for w in expired:
        expire_pending_pings(db, wave_id=w.id)
        if auto_escalate:
            new_wave = escalate_wave_to_next_tier(
                db, expired_wave=w, today=system_clock.today()
            )
            if new_wave is not None:
                escalations.append(str(new_wave.id))
    db.commit()
    return {
        "expired_count": len(expired),
        "expired_waves": [str(w.id) for w in expired],
        "escalated_waves": escalations,
    }


@router.post(
    "/cancel-acceptance",
    summary="Reverse a previously accepted wave (donor can't make it anymore)",
)
def post_cancel_acceptance(
    donor_id: uuid.UUID = Query(...),
    wave_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    wave = cancel_outreach_acceptance(db, donor_id=donor_id, wave_id=wave_id)
    if wave is None:
        raise HTTPException(
            status_code=404,
            detail=f"No ACCEPTED wave found for donor {donor_id}",
        )
    # Re-flag the slot — the engine will pick it up on the next cycle
    db.commit()
    return {
        "wave_id": str(wave.id),
        "status": getattr(wave.status, "value", str(wave.status)),
        "message": (
            "Acceptance reversed. The cycle will re-allocate this slot on the next run."
        ),
    }


@router.post(
    "/waves/{wave_id}/force-include",
    summary="Coordinator override — add a donor to this wave",
)
def post_force_include(
    wave_id: uuid.UUID,
    donor_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    wave = db.get(OutreachWave, wave_id)
    if wave is None:
        raise HTTPException(status_code=404, detail=f"Wave {wave_id} not found")
    if wave.status != OutreachWaveStatus.ACTIVE:
        raise HTTPException(
            status_code=409, detail=f"Wave {wave_id} is {wave.status} — only ACTIVE waves accept overrides"
        )
    # Avoid dup
    existing = next(
        (p for p in wave.pings if p.donor_id == donor_id), None
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Donor {donor_id} already has a ping in this wave (response={existing.response})",
        )
    now = datetime.utcnow()
    from app.models import OutreachPing as _Ping

    ping = _Ping(
        wave_id=wave_id,
        donor_id=donor_id,
        sent_at=now,  # ready for dispatch
        expires_at=wave.expires_at,
        composite_score=0.0,
        adjusted_response_rate=0.0,
        template_key="urgent_slot_alert",
    )
    db.add(ping)
    db.commit()
    return {
        "wave_id": str(wave_id),
        "ping_id": str(ping.id),
        "donor_id": str(donor_id),
        "note": "Donor force-included by coordinator. Re-dispatch the wave to send.",
    }


@router.post(
    "/waves/{wave_id}/force-exclude",
    summary="Coordinator override — cancel a PENDING ping",
)
def post_force_exclude(
    wave_id: uuid.UUID,
    donor_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    wave = db.get(OutreachWave, wave_id)
    if wave is None:
        raise HTTPException(status_code=404, detail=f"Wave {wave_id} not found")
    ping = next(
        (
            p for p in wave.pings
            if p.donor_id == donor_id
            and getattr(p.response, "value", str(p.response)) == "pending"
        ),
        None,
    )
    if ping is None:
        raise HTTPException(
            status_code=404,
            detail=f"No PENDING ping for donor {donor_id} in wave {wave_id}",
        )
    from app.models import PingResponse as _PR

    ping.response = _PR.CANCELLED
    ping.response_at = datetime.utcnow()
    db.commit()
    return {
        "wave_id": str(wave_id),
        "ping_id": str(ping.id),
        "response": getattr(ping.response, "value", str(ping.response)),
    }


# ---------- POST /outreach/waves/{wave_id}/dispatch ----------


@router.post(
    "/waves/{wave_id}/dispatch",
    summary="Send the WhatsApp pings for an ACTIVE wave",
)
def post_dispatch_wave(
    wave_id: uuid.UUID,
    override_quiet_hours: bool = Query(
        False,
        description="EMERGENCY ONLY — push messages even during 22:00–07:00 IST quiet hours",
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Dispatch every PENDING ping in this wave via Twilio.

    Each donor gets the multilingual ``urgent_slot_alert`` template in their
    preferred language, plus a short ``ref <hex>`` token so when they reply
    YES/NO the webhook can correlate the response back to this exact wave.
    """
    stmt = (
        select(OutreachWave)
        .options(joinedload(OutreachWave.pings))
        .where(OutreachWave.id == wave_id)
    )
    wave = db.execute(stmt).unique().scalar_one_or_none()
    if wave is None:
        raise HTTPException(status_code=404, detail=f"Wave {wave_id} not found")
    if wave.status != OutreachWaveStatus.ACTIVE:
        raise HTTPException(
            status_code=409,
            detail=f"Wave {wave_id} is {wave.status} — only ACTIVE waves can dispatch",
        )

    summary = dispatch_wave(wave, db=db, override_quiet_hours=override_quiet_hours)
    db.commit()
    return {
        "wave_id": str(summary.wave_id),
        "pings_sent": summary.pings_sent,
        "pings_suppressed_quiet_hours": summary.pings_suppressed_quiet_hours,
        "pings_failed": summary.pings_failed,
    }


# ---------- POST /outreach/confirm + /outreach/decline (manual close) ----------


@router.post(
    "/confirm",
    summary="Manually close a wave with an ACCEPTED response (coordinator override)",
)
def post_confirm_acceptance(
    donor_id: uuid.UUID = Query(..., description="The donor who accepted"),
    slot_ref: Optional[str] = Query(
        None, description="Slot ref token — if omitted, picks the donor's most recent PENDING ping"
    ),
    db: Session = Depends(get_db),
) -> dict:
    wave = confirm_outreach_acceptance(db, donor_id=donor_id, slot_ref=slot_ref)
    if wave is None:
        raise HTTPException(
            status_code=404,
            detail=f"No PENDING ping for donor {donor_id}",
        )
    db.commit()
    return {
        "wave_id": str(wave.id),
        "status": getattr(wave.status, "value", str(wave.status)),
        "resolved_by_donor_id": (
            str(wave.resolved_by_donor_id) if wave.resolved_by_donor_id else None
        ),
    }


@router.post(
    "/decline",
    summary="Manually close a ping with a DECLINED response (coordinator override)",
)
def post_record_decline(
    donor_id: uuid.UUID = Query(...),
    slot_ref: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    ping = record_outreach_decline(db, donor_id=donor_id, slot_ref=slot_ref)
    if ping is None:
        raise HTTPException(
            status_code=404,
            detail=f"No PENDING ping for donor {donor_id}",
        )
    db.commit()
    return {
        "ping_id": str(ping.id),
        "wave_id": str(ping.wave_id),
        "response": getattr(ping.response, "value", str(ping.response)),
    }


# ---------- Emergency button (Tier EMERGENCY) ----------


class AllocationSelection(BaseModel):
    """One per (patient, slot) the coordinator wants to actually persist."""

    patient_id: uuid.UUID
    slot_date: date
    donor_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=50)


class CommitAllocationsRequest(BaseModel):
    """Body for POST /outreach/commit-allocations.

    Lets coordinators run a dry-run cycle in the UI, *edit the proposed
    batches* (deselect allocations, remove donors, add donors), then commit
    only the curated set instead of all-or-nothing.
    """

    selections: list[AllocationSelection] = Field(..., min_length=1)
    triggered_by: str = Field(
        default="coordinator_manual",
        description="Audit label written to OutreachWave.triggered_by",
    )


@router.post(
    "/commit-allocations",
    summary="Materialise a coordinator-curated set of allocations as waves",
)
def post_commit_allocations(
    payload: CommitAllocationsRequest, db: Session = Depends(get_db)
) -> dict:
    """Replaces the all-or-nothing behaviour of `run-cycle?dry_run=false`.

    For each selection the coordinator approved:
      1. Re-validate patient + donor existence + active state + ABO compatibility
      2. Re-compute the urgency tier against today's date (the dry-run preview
         may be a few minutes stale)
      3. Build a ``WaveAllocation`` with the coordinator's chosen donor batch
      4. Persist via the same ``materialise_allocation`` path as the auto cycle

    Returns the list of wave ids that were created, plus per-selection
    diagnostics so the UI can show what got dropped (and why).
    """
    from app.outreach.engine import OpenSlot, ScoredCandidate, WaveAllocation, materialise_allocation
    from app.outreach.scoring import (
        adjusted_response_rate,
        p_accept,
        target_p_accept_for,
        urgency_for_patient,
    )
    from app.recommender.engine import _can_donate_to
    from app.models import (
        Donor as _Donor,
        OutreachTier as _OutreachTier,
        Patient as _Patient,
    )

    today = system_clock.today()
    created_waves: list[str] = []
    diagnostics: list[dict] = []

    for sel in payload.selections:
        patient = db.get(_Patient, sel.patient_id)
        if patient is None:
            diagnostics.append(
                {"patient_id": str(sel.patient_id), "skipped_reason": "patient_not_found"}
            )
            continue
        if not patient.active:
            diagnostics.append(
                {"patient_id": str(sel.patient_id), "skipped_reason": "patient_inactive"}
            )
            continue

        # Re-compute urgency at commit time (preview may be a few minutes stale)
        cadence = patient.transfusion_cadence_days or 18
        urgency = urgency_for_patient(sel.slot_date, cadence, today=today)
        slot = OpenSlot(
            patient=patient, bridge=patient.bridge,
            slot_date=sel.slot_date, urgency=urgency,
        )

        # Resolve + validate donors. We respect ABO compatibility hard-stops
        # but let the coordinator override social cooldown / fatigue (that's
        # the whole point of allowing manual curation).
        donors: list[_Donor] = []
        dropped: list[str] = []
        for did in sel.donor_ids:
            donor = db.get(_Donor, did)
            if donor is None:
                dropped.append(f"{did}: not_found")
                continue
            if not donor.is_active:
                dropped.append(f"{donor.name}: inactive")
                continue
            if not _can_donate_to(donor.blood_group, patient.blood_group):
                dropped.append(f"{donor.name}: blood_group_incompatible")
                continue
            # Clinical 90-day deferral NEVER waived
            if donor.last_donation_date is not None:
                days_since = (today - donor.last_donation_date).days
                if days_since < 90:
                    dropped.append(f"{donor.name}: within_90d_deferral")
                    continue
            donors.append(donor)

        if not donors:
            diagnostics.append(
                {
                    "patient_id": str(sel.patient_id),
                    "skipped_reason": "no_eligible_donors_after_validation",
                    "dropped": dropped,
                }
            )
            continue

        scored = [
            ScoredCandidate(
                donor=d, composite=0.5,  # placeholder — coordinator curated this
                churn_90d=0.5, survival_30d=0.5,
            )
            for d in donors
        ]
        rates = [adjusted_response_rate(d, 0.5) for d in donors]
        realised = p_accept(rates)
        allocation = WaveAllocation(
            slot=slot,
            donors=donors,
            scored=scored,
            realised_p_accept=realised,
            target_p_accept=urgency.target_p_accept,
            fully_covered=realised >= urgency.target_p_accept,
        )
        wave = materialise_allocation(
            allocation, db=db, today=today,
            tier=_OutreachTier.TIER_1,
            triggered_by=payload.triggered_by,
        )
        created_waves.append(str(wave.id))
        diagnostics.append(
            {
                "patient_id": str(sel.patient_id),
                "wave_id": str(wave.id),
                "donor_count": len(donors),
                "realised_p_accept": round(realised, 4),
                "dropped": dropped,
            }
        )

    db.commit()
    return {
        "created_count": len(created_waves),
        "created_wave_ids": created_waves,
        "diagnostics": diagnostics,
    }


class EmergencyTriggerRequest(BaseModel):
    """Body for POST /outreach/emergency — the coordinator's red button."""

    patient_id: uuid.UUID
    coordinator_name: str = Field(..., min_length=1, max_length=128)
    transfusion_deadline_at: datetime
    justification: str = Field(..., min_length=1, max_length=2000)
    hospital_lat: Optional[float] = None
    hospital_lng: Optional[float] = None
    hospital_name: Optional[str] = None


@router.post(
    "/emergency",
    summary="Trigger an emergency outreach — broadcast to every reachable donor",
)
def post_trigger_emergency(
    payload: EmergencyTriggerRequest, db: Session = Depends(get_db)
) -> dict:
    """Big red button on the patient detail page.

    Computes the reach-window-eligible donor list given a transfusion
    deadline, audits the event in ``emergency_events`` and spawns an
    EMERGENCY-tier ``OutreachWave``. The coordinator dispatches it next
    by calling ``POST /outreach/waves/{wave_id}/dispatch?override_quiet_hours=true``.
    """
    try:
        result = trigger_emergency(
            db,
            patient_id=payload.patient_id,
            coordinator_name=payload.coordinator_name,
            transfusion_deadline_at=payload.transfusion_deadline_at,
            justification=payload.justification,
            hospital_lat=payload.hospital_lat,
            hospital_lng=payload.hospital_lng,
            hospital_name=payload.hospital_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return {
        "event_id": str(result.event.id),
        "wave_id": str(result.wave.id) if result.wave else None,
        "reachable_count": result.reachable_count,
        "pool_size_before_filter": result.pool_size_before_filter,
        "deadline_at": result.event.transfusion_deadline_at.isoformat() + "Z",
        "reach_window_min": result.event.reach_window_min,
        "status": getattr(result.event.status, "value", str(result.event.status)),
    }


# ---------- Phase B: per-ping follow-up visibility + manual trigger ----------


@router.get(
    "/pings/{ping_id}/follow-ups",
    summary="Follow-up timeline for one ping (nudges + reminder + thank-you)",
)
def get_ping_follow_ups(
    ping_id: uuid.UUID, db: Session = Depends(get_db)
) -> dict:
    """Return the follow-up state of a single ping. The /outreach/[id] page
    renders this as a sent → nudged → reminded → thanked timeline."""
    from app.models import OutreachPing

    ping = db.get(OutreachPing, ping_id)
    if ping is None:
        raise HTTPException(status_code=404, detail=f"Ping {ping_id} not found")

    def _ts(dt):
        return dt.isoformat() + "Z" if dt else None

    return {
        "ping_id": str(ping.id),
        "wave_id": str(ping.wave_id),
        "donor_id": str(ping.donor_id),
        "response": getattr(ping.response, "value", str(ping.response)),
        "sent_at": _ts(ping.sent_at),
        "response_at": _ts(ping.response_at),
        "nudge": {
            "count": ping.nudge_count or 0,
            "last_sent_at": _ts(ping.last_nudge_at),
        },
        "reminder": {"sent_at": _ts(ping.reminder_sent_at)},
        "thank_you": {"sent_at": _ts(ping.thank_you_sent_at)},
    }


@router.post(
    "/pings/{ping_id}/follow-ups/nudge",
    summary="Manually trigger the pending-ping nudge for one ping (demo button)",
)
def post_send_nudge(
    ping_id: uuid.UUID, db: Session = Depends(get_db)
) -> dict:
    """Force-send a nudge regardless of the 4h / 12h / cap thresholds.

    Useful for the demo "Run now" path and for coordinators who want to
    chase a specific donor manually. Still respects donor missing phone /
    Twilio failure semantics.
    """
    from app.models import OutreachPing
    from datetime import datetime as _dt
    from app.outreach.followups import send_pending_nudge

    ping = db.get(OutreachPing, ping_id)
    if ping is None:
        raise HTTPException(status_code=404, detail=f"Ping {ping_id} not found")

    sent = send_pending_nudge(db, ping=ping, now=_dt.utcnow())
    db.commit()
    return {
        "ping_id": str(ping.id),
        "sent": sent,
        "nudge_count": ping.nudge_count or 0,
        "last_nudge_at": ping.last_nudge_at.isoformat() + "Z"
        if ping.last_nudge_at
        else None,
    }


@router.get(
    "/emergency/{event_id}",
    summary="Inspect an emergency event with its current wave state",
)
def get_emergency_status(
    event_id: uuid.UUID, db: Session = Depends(get_db)
) -> dict:
    event = get_emergency_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Emergency event {event_id} not found")
    wave: Optional[OutreachWave] = (
        db.get(OutreachWave, event.wave_id) if event.wave_id else None
    )
    return {
        "event_id": str(event.id),
        "patient_id": str(event.patient_id),
        "hospital_name": event.hospital_name,
        "triggered_by": event.triggered_by,
        "triggered_at": event.triggered_at.isoformat() + "Z",
        "transfusion_deadline_at": event.transfusion_deadline_at.isoformat() + "Z",
        "reach_window_min": event.reach_window_min,
        "justification": event.justification,
        "pool_size_at_trigger": event.pool_size_at_trigger,
        "status": getattr(event.status, "value", str(event.status)),
        "accepted_donor_id": (
            str(event.accepted_donor_id) if event.accepted_donor_id else None
        ),
        "accepted_at": event.accepted_at.isoformat() + "Z" if event.accepted_at else None,
        "wave": _wave_to_summary(wave) if wave else None,
    }


