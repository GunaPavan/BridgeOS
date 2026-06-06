"""Alert Allocator — donor outreach engine.

The allocator solves "how many donors to ping, which ones, on what channel,
and when" — under contention (many patients sharing the same donor pool)
and under deadline pressure (variable per-patient transfusion cadences).

The whole pipeline is automated: waves dispatch via WhatsApp, expire on a
timer, and auto-escalate to the next tier (wider pool, softer template).
There is no human phone-team handoff — the only manual hook is the
EMERGENCY button for coordinator-triggered geo-broadcasts.

The math + eligibility filters live in ``app.outreach.scoring``.
The OR-Tools CP-SAT global allocator lives in ``app.outreach.engine``.
The wave/ping state lives in ``app.models.outreach``.
"""

from app.outreach.dispatch import (
    DispatchSummary,
    cancel_outreach_acceptance,
    confirm_outreach_acceptance,
    dispatch_wave,
    expire_pending_pings,
    is_quiet_hours,
    make_slot_ref,
    parse_slot_ref,
    record_outreach_decline,
)
from app.outreach.emergency import (
    EmergencyTriggerResult,
    ReachableDonor,
    can_reach_in_time,
    estimate_travel_min,
    find_reachable_donors,
    get_emergency_event,
    trigger_emergency,
)
from app.outreach.scoring import (
    UrgencyContext,
    adjusted_response_rate,
    composite_score,
    has_active_cooldown,
    is_eligible_for_outreach,
    minimal_batch,
    p_accept,
    target_p_accept_for,
    urgency_for_patient,
)

__all__ = [
    "UrgencyContext",
    "adjusted_response_rate",
    "composite_score",
    "has_active_cooldown",
    "is_eligible_for_outreach",
    "minimal_batch",
    "p_accept",
    "target_p_accept_for",
    "urgency_for_patient",
    # Dispatch + close
    "DispatchSummary",
    "cancel_outreach_acceptance",
    "confirm_outreach_acceptance",
    "dispatch_wave",
    "expire_pending_pings",
    "is_quiet_hours",
    "make_slot_ref",
    "parse_slot_ref",
    "record_outreach_decline",
    # Emergency
    "EmergencyTriggerResult",
    "ReachableDonor",
    "can_reach_in_time",
    "estimate_travel_min",
    "find_reachable_donors",
    "get_emergency_event",
    "trigger_emergency",
]
