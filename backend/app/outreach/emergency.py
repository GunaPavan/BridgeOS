"""Phase E — Coordinator-triggered emergency broadcast.

Different problem from "scheduled transfusion approaching":

  Scheduled outreach (Tiers 1–3) → optimised under cost (don't burn donors)
  Emergency outreach (this module) → optimised under deadline (every reachable
                                     donor gets pinged at once, social
                                     cooldowns + quiet hours waived)

The big red EMERGENCY button on the patient detail page calls
``trigger_emergency``. Behind that one call:

  1. Compute hospital location (defaults to the patient's `lat`/`lng`, since
     in our dataset the patient row IS the hospital location)
  2. Filter the donor pool by ABO/Rh compatibility + clinical 90-day deferral
     (the only two filters that never waive)
  3. Add the reach-window calc — donor must be physically able to arrive by
     ``transfusion_deadline_at - 30 min prep`` given haversine distance and
     a 25 km/h urban-travel estimate
  4. Create an EmergencyEvent audit row + a high-tier OutreachWave with
     ``triggered_by="emergency_button"`` and ``tier=EMERGENCY``
  5. Materialise pings for every reachable donor (no batch cap)
  6. Subsequent ``POST /outreach/waves/{id}/dispatch?override_quiet_hours=true``
     sends them

The eRaktKosh / ICMR fallback fires in parallel — coordinator gets the donor
list AND a hospital-bank inventory snapshot at the same time so the phone
team can work both angles.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.ml.utils import haversine_km
from app.models import (
    Donor,
    EmergencyEvent,
    EmergencyEventStatus,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    UrgencyTier,
)
from app.outreach.engine import OpenSlot, materialise_allocation
from app.outreach.scoring import (
    UrgencyContext,
    adjusted_response_rate,
    composite_score,
    is_eligible_for_outreach,
    p_accept,
    precompute_active_bridge_memberships,
    precompute_active_cooldowns,
    precompute_recent_ping_counts,
)

logger = logging.getLogger(__name__)


# Urban travel-time estimate — conservative because real urban Indian traffic
# averages 20–30 km/h. The 25 in the middle is what we use for the reach
# window. Plus a flat 30 min for parking + hospital check-in.
TRAVEL_AVG_KMH = 25.0
HOSPITAL_PREP_MIN = 30


@dataclass(frozen=True)
class ReachableDonor:
    donor: Donor
    distance_km: float
    travel_min: float
    composite: float

    @property
    def reach_min(self) -> float:
        return self.travel_min + HOSPITAL_PREP_MIN


def estimate_travel_min(distance_km: float, kmh: float = TRAVEL_AVG_KMH) -> float:
    """Distance / average speed → minutes. Includes the per-trip prep buffer."""
    if distance_km <= 0:
        return 0.0
    return (distance_km / kmh) * 60.0


def can_reach_in_time(
    distance_km: float,
    *,
    deadline_at: datetime,
    now: Optional[datetime] = None,
) -> bool:
    """Donor at ``distance_km`` from hospital — will they make it by deadline?

    Includes the flat 30-min hospital prep window. Returns False on negative
    reach (already too late).
    """
    now = now or datetime.utcnow()
    travel_min = estimate_travel_min(distance_km)
    minutes_to_deadline = (deadline_at - now).total_seconds() / 60.0
    return minutes_to_deadline >= (travel_min + HOSPITAL_PREP_MIN)


def find_reachable_donors(
    db: Session,
    *,
    patient: Patient,
    hospital_lat: float,
    hospital_lng: float,
    deadline_at: datetime,
    now: Optional[datetime] = None,
) -> list[ReachableDonor]:
    """Eligible donors who can physically reach the hospital by deadline.

    Sorted by composite quality (closer + more responsive + Kell-match donors first).
    """
    now = now or datetime.utcnow()

    donor_pool = list(
        db.execute(select(Donor).where(Donor.is_active.is_(True))).scalars().all()
    )
    cooldown_lookup = precompute_active_cooldowns(db)
    recent_ping_counts = precompute_recent_ping_counts(db)
    active_bridge_memberships = precompute_active_bridge_memberships(db)

    reachable: list[ReachableDonor] = []
    today_d = (now or datetime.utcnow()).date()
    for donor in donor_pool:
        if not is_eligible_for_outreach(
            donor, patient, today=today_d, db=db, emergency=True,
            cooldown_lookup=cooldown_lookup,
        ):
            continue
        if not donor.lat or not donor.lng:
            continue
        distance_km = haversine_km(
            donor.lat, donor.lng, hospital_lat, hospital_lng
        )
        if not can_reach_in_time(distance_km, deadline_at=deadline_at, now=now):
            continue
        travel = estimate_travel_min(distance_km)
        # Score them for ranking — same composite shape, just for ordering
        s = composite_score(
            donor, patient, db=db,
            churn_90d=0.0,  # emergency overrides ML — we're picking by reachability
            survival_30d=0.0,
            today=today_d,
            bridge_id=patient.bridge.id if patient.bridge else None,
            recent_ping_counts=recent_ping_counts,
            active_bridge_memberships=active_bridge_memberships,
        )
        reachable.append(
            ReachableDonor(donor=donor, distance_km=distance_km, travel_min=travel, composite=s)
        )

    # Sort by closest first (distance), then composite desc — the coordinator
    # sees the easiest-to-reach donors at the top of the wave
    reachable.sort(key=lambda r: (r.distance_km, -r.composite))
    return reachable


@dataclass(frozen=True)
class EmergencyTriggerResult:
    event: EmergencyEvent
    wave: Optional[OutreachWave]
    reachable_count: int
    pool_size_before_filter: int
    eraktkosh_banks: list = None  # type: ignore[assignment]
    icmr_rare_donors: list = None  # type: ignore[assignment]


def trigger_emergency(
    db: Session,
    *,
    patient_id: uuid.UUID,
    coordinator_name: str,
    transfusion_deadline_at: datetime,
    justification: str,
    hospital_lat: Optional[float] = None,
    hospital_lng: Optional[float] = None,
    hospital_name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> EmergencyTriggerResult:
    """Coordinator pressed the red button.

    Creates the EmergencyEvent audit row, computes the reachable-donor list,
    and (if any donors qualify) spawns an EMERGENCY-tier OutreachWave with
    pings ready for dispatch. Dispatch is a separate call so the coordinator
    can sanity-check the list before pushing 30+ WhatsApps out the door.
    """
    now = now or datetime.utcnow()
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise ValueError(f"Patient {patient_id} not found")

    # Default the hospital coords to the patient row (our dataset stores the
    # hospital location on the patient — there's no separate Hospital table)
    h_lat = hospital_lat if hospital_lat is not None else patient.lat
    h_lng = hospital_lng if hospital_lng is not None else patient.lng
    h_name = hospital_name or patient.hospital or "Unknown hospital"

    minutes_to_deadline = (transfusion_deadline_at - now).total_seconds() / 60.0
    if minutes_to_deadline <= 0:
        raise ValueError("Deadline already passed")

    # Pool size BEFORE the reach filter — for the audit log + UI counter
    pool_size_before = db.execute(
        select(Donor).where(Donor.is_active.is_(True))
    ).scalars().all()
    pool_size_before_n = len(pool_size_before)

    reachable = find_reachable_donors(
        db, patient=patient, hospital_lat=h_lat, hospital_lng=h_lng,
        deadline_at=transfusion_deadline_at, now=now,
    )

    # Parallel external fanout — fire whether we have reachable donors or not,
    # because zero-reachable is precisely when the phone team needs the
    # eRaktKosh inventory + ICMR rare-donor list to fall back on
    eraktkosh_banks: list = []
    icmr_rare_donors: list = []
    try:
        from app.integrations import eraktkosh, icmr_rdri

        bg_value = getattr(patient.blood_group, "value", str(patient.blood_group))
        eraktkosh_banks = list(
            eraktkosh.fetch_inventory(city=patient.city, blood_group=bg_value) or []
        )
        icmr_rare_donors = list(
            icmr_rdri.lookup_donors(
                blood_group=bg_value,
                kell_negative=patient.kell_negative,
                city=patient.city,
            )
            or []
        )
    except Exception:  # pragma: no cover — external fanout shouldn't block
        logger.exception("eRaktKosh/ICMR fanout failed on emergency trigger")

    event = EmergencyEvent(
        patient_id=patient.id,
        triggered_by=coordinator_name,
        triggered_at=now,
        hospital_name=h_name,
        hospital_lat=h_lat,
        hospital_lng=h_lng,
        transfusion_deadline_at=transfusion_deadline_at,
        reach_window_min=int(minutes_to_deadline),
        justification=justification,
        pool_size_at_trigger=len(reachable),
        status=EmergencyEventStatus.ACTIVE,
    )
    db.add(event)
    db.flush()

    if not reachable:
        logger.warning("Emergency for patient %s — no reachable donors", patient.id)
        db.flush()
        return EmergencyTriggerResult(
            event=event, wave=None, reachable_count=0,
            pool_size_before_filter=pool_size_before_n,
            eraktkosh_banks=eraktkosh_banks,
            icmr_rare_donors=icmr_rare_donors,
        )

    # Spawn an OutreachWave at EMERGENCY tier — every reachable donor gets a
    # ping (no minimal-batch cap; emergency overrides the cost optimisation)
    slot_date = transfusion_deadline_at.date()
    urgency = UrgencyContext(
        tier=UrgencyTier.CRITICAL,
        gap_days=0,
        cadence_days=patient.transfusion_cadence_days or 18,
        ratio=0.0,
        target_p_accept=0.99,
        max_batch_size=len(reachable),
    )
    slot = OpenSlot(
        patient=patient, bridge=patient.bridge,
        slot_date=slot_date, urgency=urgency,
    )
    # Build the allocation manually — no minimal-batch, every reachable donor
    # is in the wave
    from app.outreach.engine import ScoredCandidate, WaveAllocation

    scored = [
        ScoredCandidate(donor=r.donor, composite=r.composite, churn_90d=0.0, survival_30d=0.0)
        for r in reachable
    ]
    rates = [adjusted_response_rate(r.donor, 0.0) for r in reachable]
    realised = p_accept(rates)
    allocation = WaveAllocation(
        slot=slot,
        donors=[r.donor for r in reachable],
        scored=scored,
        realised_p_accept=realised,
        target_p_accept=urgency.target_p_accept,
        fully_covered=realised >= urgency.target_p_accept,
    )
    wave = materialise_allocation(
        allocation, db=db, today=now.date(),
        tier=OutreachTier.EMERGENCY,
        triggered_by="emergency_button",
    )
    # Link the event ↔ wave (bidirectional reference for audit)
    event.wave_id = wave.id
    db.flush()

    return EmergencyTriggerResult(
        event=event, wave=wave,
        reachable_count=len(reachable),
        pool_size_before_filter=pool_size_before_n,
        eraktkosh_banks=eraktkosh_banks,
        icmr_rare_donors=icmr_rare_donors,
    )


def get_emergency_event(db: Session, event_id: uuid.UUID) -> Optional[EmergencyEvent]:
    return db.get(EmergencyEvent, event_id)
