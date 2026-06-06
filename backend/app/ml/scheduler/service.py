"""Bridge → solver glue. Loads ORM rows, calls the pure solver, returns ScheduleResult."""

from __future__ import annotations

from datetime import date

from app.ml.scheduler.solver import DonorInput, ScheduleResult, solve_rotation
from app.ml.utils import haversine_km
from app.models import Bridge, MembershipStatus


def compute_schedule_for_bridge(
    bridge: Bridge,
    today: date,
    horizon_days: int = 365,
    time_limit_seconds: float = 5.0,
) -> ScheduleResult:
    """Build solver inputs from a Bridge ORM row and run the solver."""
    patient = bridge.patient
    active_members = [
        m for m in bridge.memberships if m.status == MembershipStatus.ACTIVE
    ]
    donors = [
        DonorInput(
            donor_id=m.donor.id,
            name=m.donor.name,
            blood_group=m.donor.blood_group.value
            if hasattr(m.donor.blood_group, "value")
            else str(m.donor.blood_group),
            last_donation_date=m.donor.last_donation_date,
            response_rate=float(m.donor.response_rate),
            distance_km=haversine_km(
                m.donor.lat, m.donor.lng, patient.lat, patient.lng
            ),
        )
        for m in active_members
    ]
    return solve_rotation(
        donors=donors,
        last_transfusion_date=patient.last_transfusion_date,
        cadence_days=patient.transfusion_cadence_days,
        today=today,
        horizon_days=horizon_days,
        time_limit_seconds=time_limit_seconds,
    )
