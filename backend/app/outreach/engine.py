"""Global allocator — the per-cycle solver.

One ``run_cycle`` call:

    1. Pulls every patient whose next-transfusion slot is inside the horizon
    2. Classifies each into an ``UrgencyContext``
    3. For each, builds a ranked candidate pool (eligibility-filtered, composite-scored)
    4. Sorts patients by (urgency, rarity, gap_days) and runs a greedy
       global assignment that respects the "≤ 1 ping per donor per cycle" rule
    5. Materialises each allocation as a persistent ``OutreachWave`` + N
       ``OutreachPing`` rows ready to be dispatched by Phase C

This is the keystone module of the Alert Allocator. The ML predictors are
optional — when ``app.ml.churn`` isn't loaded, the allocator falls back to
the neutral churn=0.5 prior, which keeps unit tests fast and the system
fully functional even without trained models.

The greedy formulation matches what OR-Tools CP-SAT would converge to at
hackathon scale (80 patients × 7,000 donors → ~6M ops, sub-second). A
CP-SAT lift can land in Phase F polish if we want provably-optimal output.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import (
    Bridge,
    Donor,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    UrgencyTier,
)
from app.outreach.scoring import (
    UrgencyContext,
    adjusted_response_rate,
    composite_score,
    is_eligible_for_outreach,
    max_batch_for,
    minimal_batch,
    p_accept,
    precompute_active_bridge_memberships,
    precompute_active_cooldowns,
    precompute_recent_ping_counts,
    target_p_accept_for,
    urgency_for_patient,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1 — collect open slots
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpenSlot:
    """One patient slot in need of donor coverage."""

    patient: Patient
    bridge: Optional[Bridge]
    slot_date: date
    urgency: UrgencyContext

    @property
    def patient_id(self) -> uuid.UUID:
        return self.patient.id

    @property
    def bridge_id(self) -> Optional[uuid.UUID]:
        return self.bridge.id if self.bridge else None


def collect_open_slots(
    db: Session,
    *,
    today: date,
    horizon_days: int = 7,
) -> list[OpenSlot]:
    """All patients whose next transfusion is inside the horizon and doesn't
    already have an ACTIVE wave covering it.

    PLANNED slots are dropped — the rotation scheduler (Phase 5) owns them.
    """
    horizon = today + timedelta(days=horizon_days)

    patient_stmt = select(Patient).where(Patient.active.is_(True))
    patients = db.execute(patient_stmt).scalars().all()

    # Pre-load active waves keyed by (patient_id, slot_date)
    active_wave_stmt = select(OutreachWave).where(
        OutreachWave.status == OutreachWaveStatus.ACTIVE
    )
    active_waves = db.execute(active_wave_stmt).scalars().all()
    covered_slots = {(w.patient_id, w.slot_date) for w in active_waves}

    open_slots: list[OpenSlot] = []
    for p in patients:
        if not p.last_transfusion_date or not p.transfusion_cadence_days:
            continue
        next_date = p.last_transfusion_date + timedelta(days=p.transfusion_cadence_days)
        if next_date > horizon:
            continue
        # Already actively covered?
        if (p.id, next_date) in covered_slots:
            continue
        urgency = urgency_for_patient(next_date, p.transfusion_cadence_days, today=today)
        if urgency.tier == UrgencyTier.PLANNED:
            continue
        bridge = p.bridge
        open_slots.append(
            OpenSlot(patient=p, bridge=bridge, slot_date=next_date, urgency=urgency)
        )
    return open_slots


# ---------------------------------------------------------------------------
# Step 2 — score the candidate pool per patient
# ---------------------------------------------------------------------------


# ----- Module-level TTL caches for the ML score getters -----
# The bottleneck of `run_cycle` on the real Blood Warriors dataset is the
# XGBoost / GradientBoostingSurvival batch predict over ~6,000 donors —
# 13 s combined cold. The predictions don't change minute-to-minute (model
# artefacts are static; donor features change slowly), so caching pool-wide
# scores for a few minutes makes subsequent cycles instant.
_CHURN_CACHE: dict[str, tuple[float, dict[uuid.UUID, float]]] = {}
_SURVIVAL_CACHE: dict[str, tuple[float, dict[uuid.UUID, float]]] = {}
_ML_CACHE_TTL_SEC = 300  # 5 minutes


def _pool_signature(donors: list[Donor]) -> str:
    """Cheap stable hash of the pool so cache invalidates when donors change.

    Uses (count, max(updated_at-equivalent_signal)) — a hash of the donor
    last_contacted/last_donation fingerprint. Two pools with the same
    signature are functionally identical for prediction purposes.
    """
    # Use a sample-based hash so we don't iterate all 6,000 donors twice
    # per cycle. The signature catches added/removed donors and
    # last_contacted_date updates from the response feedback loop.
    return f"{len(donors)}|{hash(tuple((d.id, d.last_contacted_date, d.last_donation_date) for d in donors[:200]))}"


def get_churn_scores(donors: Iterable[Donor]) -> dict[uuid.UUID, float]:
    """Run the churn predictor over the pool and return ``donor.id -> churn_90d``.

    Cached for 5 minutes per pool-signature — typical demo cycle hits the
    cache. Returns an empty dict if the predictor isn't loaded; callers
    then fall back to the conservative ``churn=0.5`` prior.
    """
    import time as _time

    donors_list = list(donors)
    if not donors_list:
        return {}

    sig = _pool_signature(donors_list)
    cached = _CHURN_CACHE.get(sig)
    if cached is not None and (_time.time() - cached[0]) < _ML_CACHE_TTL_SEC:
        return cached[1]

    try:
        from app.ml.churn import load_predictor as load_churn

        predictor = load_churn()
        if predictor is None:
            logger.warning("No churn predictor loaded — falling back to neutral prior.")
            return {}
        preds = predictor.predict_batch(donors_list)
        result = {d.id: max(0.0, min(1.0, 1.0 - p.p_active)) for d, p in zip(donors_list, preds)}
        _CHURN_CACHE[sig] = (_time.time(), result)
        return result
    except Exception:  # pragma: no cover — defensive
        logger.exception("Churn scoring failed; falling back to neutral prior")
        return {}


def get_survival_scores(donors: Iterable[Donor]) -> dict[uuid.UUID, float]:
    """30-day survival probability per donor. Cached for 5 minutes per
    pool-signature; empty dict on no predictor."""
    import time as _time

    donors_list = list(donors)
    if not donors_list:
        return {}

    sig = _pool_signature(donors_list)
    cached = _SURVIVAL_CACHE.get(sig)
    if cached is not None and (_time.time() - cached[0]) < _ML_CACHE_TTL_SEC:
        return cached[1]

    try:
        from app.ml.survival import load_predictor as load_surv

        predictor = load_surv()
        if predictor is None:
            return {}
        preds = predictor.predict_batch(donors_list)
        result = {d.id: max(0.0, min(1.0, p.p_survive_30d)) for d, p in zip(donors_list, preds)}
        _SURVIVAL_CACHE[sig] = (_time.time(), result)
        return result
    except Exception:
        return {}


def invalidate_ml_cache() -> None:
    """Force the next ``get_churn_scores`` / ``get_survival_scores`` call to
    re-run the predictors. Useful in tests + for manual coordinator override."""
    _CHURN_CACHE.clear()
    _SURVIVAL_CACHE.clear()


@dataclass(frozen=True)
class ScoredCandidate:
    donor: Donor
    composite: float
    churn_90d: float
    survival_30d: float


def score_candidates(
    slot: OpenSlot,
    *,
    db: Session,
    today: date,
    churn_scores: dict[uuid.UUID, float],
    survival_scores: dict[uuid.UUID, float],
    emergency: bool = False,
    # Per-cycle caches — when omitted, ``score_candidates`` reads the pool
    # itself and computes everything from scratch (used by ad-hoc callers
    # and tests). Passing all four caches turns each per-donor call from
    # ~3 DB queries into pure memory lookups.
    donor_pool: Optional[list[Donor]] = None,
    cooldown_lookup: Optional[dict[tuple[uuid.UUID, Optional[uuid.UUID]], bool]] = None,
    recent_ping_counts: Optional[dict[uuid.UUID, int]] = None,
    active_bridge_memberships: Optional[dict[uuid.UUID, set[uuid.UUID]]] = None,
) -> list[ScoredCandidate]:
    """Pull the donor pool, eligibility-filter, score, and sort descending.

    The pool is scoped to active donors. Compatibility, deferral, cooldown
    and fatigue gates run inside ``is_eligible_for_outreach``.
    """
    if donor_pool is None:
        donor_pool = list(
            db.execute(select(Donor).where(Donor.is_active.is_(True))).scalars().all()
        )
    scored: list[ScoredCandidate] = []
    for d in donor_pool:
        if not is_eligible_for_outreach(
            d, slot.patient, today=today, db=db, emergency=emergency,
            bridge_id=slot.bridge_id,
            cooldown_lookup=cooldown_lookup,
        ):
            continue
        churn = churn_scores.get(d.id, 0.5)
        surv = survival_scores.get(d.id, 0.5)
        s = composite_score(
            d, slot.patient,
            db=db,
            churn_90d=churn,
            survival_30d=surv,
            today=today,
            bridge_id=slot.bridge_id,
            recent_ping_counts=recent_ping_counts,
            active_bridge_memberships=active_bridge_memberships,
        )
        scored.append(
            ScoredCandidate(donor=d, composite=s, churn_90d=churn, survival_30d=surv)
        )
    scored.sort(key=lambda x: x.composite, reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Step 3 — global allocator (greedy with conflict resolution)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WaveAllocation:
    """The solver's output for one slot — donors selected + math diagnostics."""

    slot: OpenSlot
    donors: list[Donor]
    scored: list[ScoredCandidate]  # full ranked candidate list (for debug + UI)
    realised_p_accept: float
    target_p_accept: float
    fully_covered: bool

    @property
    def shortfall(self) -> float:
        return max(0.0, self.target_p_accept - self.realised_p_accept)


_URGENCY_ORDER = {
    UrgencyTier.CRITICAL: 0,
    UrgencyTier.HIGH: 1,
    UrgencyTier.MEDIUM: 2,
    UrgencyTier.PLANNED: 3,
}


def _is_broken_bridge(slot: OpenSlot) -> bool:
    """Structural failure proxy — bridges with fewer than 5 active donors are
    classified CRITICAL in `bridge.health`, and that's the data-derived proxy
    we use for "broken" without needing a separate enum or the raw
    ``status_of_bridge`` column.
    """
    if slot.bridge is None:
        return False
    try:
        from app.models import BridgeHealth

        return slot.bridge.health == BridgeHealth.CRITICAL
    except Exception:
        return False


def _slot_priority_key(slot: OpenSlot, scored: list[ScoredCandidate]) -> tuple:
    """Sort key — earlier in the order = higher priority for allocation.

    Tie-breaks:
      0. Broken-bridge structural failure (active_donor_count < 5 -> CRITICAL
         bridge.health) goes first regardless of urgency tier. A bridge with no
         redundancy is a hard operational failure, not a scheduling delay.
      1. Urgency tier (CRITICAL < HIGH < MEDIUM)
      2. Pool rarity (smaller pool = served first; protects the rare-bg patient)
      3. gap_days asc (sooner deadline = first within tier)
    """
    return (
        0 if _is_broken_bridge(slot) else 1,
        _URGENCY_ORDER.get(slot.urgency.tier, 99),
        len(scored),
        slot.urgency.gap_days,
    )


def solve_outreach_cycle(
    open_slots: list[OpenSlot],
    *,
    db: Session,
    today: date,
    churn_scores: Optional[dict[uuid.UUID, float]] = None,
    survival_scores: Optional[dict[uuid.UUID, float]] = None,
    emergency: bool = False,
) -> list[WaveAllocation]:
    """One cycle of global allocation.

    Greedy: sort slots by (urgency, rarity, gap). For each slot, pick the
    minimal batch from candidates not already claimed in this cycle. This
    guarantees the per-donor-per-cycle cap of 1 and respects urgency.

    Returns one ``WaveAllocation`` per slot (donors may be empty if pool
    exhausted — caller decides whether to escalate tier next cycle).
    """
    # ------- Pre-compute the per-cycle caches once -------
    # The pool, ML scores, and lookup tables are all global to the cycle —
    # computing them once is the difference between sub-second runs and the
    # ~60s "9 minutes of N+1 queries" failure mode.
    donor_pool = list(
        db.execute(select(Donor).where(Donor.is_active.is_(True))).scalars().all()
    )
    if churn_scores is None:
        churn_scores = get_churn_scores(donor_pool)
    if survival_scores is None:
        survival_scores = get_survival_scores(donor_pool)
    cooldown_lookup = precompute_active_cooldowns(db)
    recent_ping_counts = precompute_recent_ping_counts(db)
    active_bridge_memberships = precompute_active_bridge_memberships(db)

    # Score every slot's candidate pool first
    scored_per_slot: list[tuple[OpenSlot, list[ScoredCandidate]]] = []
    for slot in open_slots:
        scored = score_candidates(
            slot, db=db, today=today,
            churn_scores=churn_scores,
            survival_scores=survival_scores,
            emergency=emergency,
            donor_pool=donor_pool,
            cooldown_lookup=cooldown_lookup,
            recent_ping_counts=recent_ping_counts,
            active_bridge_memberships=active_bridge_memberships,
        )
        scored_per_slot.append((slot, scored))

    # Sort by allocation priority
    scored_per_slot.sort(key=lambda item: _slot_priority_key(item[0], item[1]))

    used_donor_ids: set[uuid.UUID] = set()
    allocations: list[WaveAllocation] = []
    for slot, scored in scored_per_slot:
        # Filter out donors already claimed in this cycle
        available = [c for c in scored if c.donor.id not in used_donor_ids]
        available_donors = [c.donor for c in available]
        # Build the lookup so minimal_batch can pull the right churn_90d
        churn_lookup = {c.donor.id: c.churn_90d for c in available}
        # Multi-unit floor — if the patient needs 2+ units per transfusion
        # (real Blood Warriors data has a `quantity_required` column that
        # ingests into `Patient.units_per_transfusion`), we need that many
        # donors to actually accept, not just enough probability that ONE will.
        min_size = max(1, int(getattr(slot.patient, "units_per_transfusion", 1) or 1))
        batch = minimal_batch(
            available_donors,
            churn_scores=churn_lookup,
            target_p_accept=slot.urgency.target_p_accept,
            max_size=max(slot.urgency.max_batch_size, min_size),
            min_size=min_size,
        )
        used_donor_ids.update(d.id for d in batch)
        rates = [adjusted_response_rate(d, churn_lookup.get(d.id, 0.5)) for d in batch]
        realised = p_accept(rates)
        allocations.append(
            WaveAllocation(
                slot=slot,
                donors=batch,
                scored=scored,
                realised_p_accept=realised,
                target_p_accept=slot.urgency.target_p_accept,
                fully_covered=realised >= slot.urgency.target_p_accept,
            )
        )
    return allocations


# ---------------------------------------------------------------------------
# Step 4 — materialise allocations as wave + ping rows
# ---------------------------------------------------------------------------


def _ping_expiry_for(tier: UrgencyTier) -> timedelta:
    """How long do we wait for replies before escalating."""
    return {
        UrgencyTier.CRITICAL: timedelta(minutes=30),
        UrgencyTier.HIGH: timedelta(hours=2),
        UrgencyTier.MEDIUM: timedelta(hours=12),
        UrgencyTier.PLANNED: timedelta(hours=24),
    }.get(tier, timedelta(hours=2))


def materialise_allocation(
    allocation: WaveAllocation,
    *,
    db: Session,
    today: date,
    tier: OutreachTier = OutreachTier.TIER_1,
    triggered_by: str = "auto_cycle",
) -> OutreachWave:
    """Persist one WaveAllocation as an OutreachWave + N OutreachPing rows.

    The wave is created in ACTIVE status. Pings are PENDING. Dispatch (the
    actual WhatsApp send) happens in Phase C — this function is just the
    state-machine setup.
    """
    now = datetime.utcnow()
    wave = OutreachWave(
        patient_id=allocation.slot.patient.id,
        bridge_id=allocation.slot.bridge_id,
        slot_date=allocation.slot.slot_date,
        tier=tier,
        urgency=allocation.slot.urgency.tier,
        status=OutreachWaveStatus.ACTIVE,
        target_p_accept=allocation.target_p_accept,
        realised_p_accept=allocation.realised_p_accept,
        gap_days_at_creation=allocation.slot.urgency.gap_days,
        pool_size_at_creation=len(allocation.scored),
        triggered_by=triggered_by,
        created_at=now,
        expires_at=now + _ping_expiry_for(allocation.slot.urgency.tier),
    )
    db.add(wave)
    db.flush()

    scored_by_id = {c.donor.id: c for c in allocation.scored}
    for donor in allocation.donors:
        c = scored_by_id.get(donor.id)
        churn = c.churn_90d if c else 0.5
        composite = c.composite if c else 0.0
        ping = OutreachPing(
            wave_id=wave.id,
            donor_id=donor.id,
            sent_at=now,  # marker — dispatch will overwrite when actually sent
            expires_at=wave.expires_at,
            composite_score=composite,
            adjusted_response_rate=adjusted_response_rate(donor, churn),
            language=getattr(donor.preferred_language, "value", str(donor.preferred_language)),
        )
        db.add(ping)
    db.flush()
    return wave


# ---------------------------------------------------------------------------
# Step 5 — top-level cycle runner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CycleSummary:
    """What happened in one allocator cycle — for the API response and analytics."""

    cycle_at: datetime
    open_slots: int
    waves_created: int
    pings_planned: int
    critical_slots: int
    high_slots: int
    medium_slots: int
    fully_covered_slots: int
    shortfall_slots: int
    dry_run: bool


def run_cycle(
    db: Session,
    *,
    today: date,
    horizon_days: int = 7,
    dry_run: bool = False,
) -> tuple[CycleSummary, list[WaveAllocation]]:
    """Top-level cycle entry point.

    Always returns the allocator's verdict (list of allocations). When
    ``dry_run=True`` the function does NOT persist anything — callers use
    this for "preview" UX where coordinators see what the allocator wants
    to do before committing.
    """
    open_slots = collect_open_slots(db, today=today, horizon_days=horizon_days)
    allocations = solve_outreach_cycle(open_slots, db=db, today=today)

    if not dry_run:
        for alloc in allocations:
            if alloc.donors:
                materialise_allocation(alloc, db=db, today=today)
        db.commit()

    summary = CycleSummary(
        cycle_at=datetime.utcnow(),
        open_slots=len(open_slots),
        waves_created=sum(1 for a in allocations if a.donors),
        pings_planned=sum(len(a.donors) for a in allocations),
        critical_slots=sum(1 for a in allocations if a.slot.urgency.tier == UrgencyTier.CRITICAL),
        high_slots=sum(1 for a in allocations if a.slot.urgency.tier == UrgencyTier.HIGH),
        medium_slots=sum(1 for a in allocations if a.slot.urgency.tier == UrgencyTier.MEDIUM),
        fully_covered_slots=sum(1 for a in allocations if a.fully_covered),
        shortfall_slots=sum(1 for a in allocations if not a.fully_covered),
        dry_run=dry_run,
    )
    return summary, allocations


# ---------------------------------------------------------------------------
# Step 6 — tier escalation on expiry (run from a separate poller)
# ---------------------------------------------------------------------------


# Automated escalation ladder. Each step widens the donor pool / softens
# the template / lifts a guard. There is NO manual phone-team handoff:
# expiring a TIER_2 wave creates a TIER_3 broadcast directly.
_TIER_NEXT: dict[OutreachTier, OutreachTier] = {
    OutreachTier.TIER_1: OutreachTier.TIER_2,
    OutreachTier.TIER_2: OutreachTier.TIER_3,
    OutreachTier.TIER_3: OutreachTier.TIER_4_EXTERNAL,
}


def expire_and_escalate_waves(
    db: Session, *, now: Optional[datetime] = None
) -> list[OutreachWave]:
    """Find waves whose expiry passed without acceptance and mark them EXPIRED.

    Returns the list of newly-expired waves. Phase C wires this into a
    background cron + the API so coordinators can manually trigger.

    Note: this function only EXPIRES the previous wave. Creating the
    next-tier wave is the runtime's job — call run_cycle again after this
    sweep and the open_slots collector will see the now-uncovered patient.
    """
    now = now or datetime.utcnow()
    stmt = select(OutreachWave).where(
        and_(
            OutreachWave.status == OutreachWaveStatus.ACTIVE,
            OutreachWave.expires_at.is_not(None),
            OutreachWave.expires_at < now,
        )
    )
    expired = db.execute(stmt).scalars().all()
    for w in expired:
        w.status = OutreachWaveStatus.EXPIRED
        w.resolved_at = now
    db.flush()
    return list(expired)


def next_tier_for(current: OutreachTier) -> Optional[OutreachTier]:
    """The escalation step after a tier times out."""
    return _TIER_NEXT.get(current)


def escalate_wave_to_next_tier(
    db: Session,
    *,
    expired_wave: OutreachWave,
    today: date,
    now: Optional[datetime] = None,
) -> Optional[OutreachWave]:
    """When a wave expires without acceptance, create the next-tier wave.

    Fully automated escalation ladder — no human-in-the-loop tier:
        TIER_1 → TIER_2          (expanded WhatsApp batch, skips already-pinged donors)
        TIER_2 → TIER_3          (full-pool soft-tone broadcast)
        TIER_3 → TIER_4_EXTERNAL (no wave; coordinator alert only)

    Tier 3 uses the `final_ask_soft` template and includes the
    `inactive_limited_despite_calls` cohort (passed via emergency=True to the
    eligibility filter so the fatigue gate is bypassed). Tier 4 returns None —
    coordinator must intervene with eRaktKosh / ICMR / hospital-bank lookups.
    """
    now = now or datetime.utcnow()
    next_tier = next_tier_for(expired_wave.tier)
    if next_tier is None or next_tier == OutreachTier.TIER_4_EXTERNAL:
        return None

    patient = db.get(Patient, expired_wave.patient_id)
    if patient is None:
        return None

    # Re-classify urgency against today's gap — every escalation gets fresh urgency math
    if patient.last_transfusion_date and patient.transfusion_cadence_days:
        next_date = patient.last_transfusion_date + timedelta(
            days=patient.transfusion_cadence_days
        )
    else:
        next_date = expired_wave.slot_date
    urgency = urgency_for_patient(
        next_date, patient.transfusion_cadence_days or 18, today=today
    )
    # If the slot is now PLANNED (out of horizon), we don't escalate — the
    # rotation scheduler picks it up
    if urgency.tier == UrgencyTier.PLANNED:
        return None

    slot = OpenSlot(
        patient=patient,
        bridge=patient.bridge,
        slot_date=expired_wave.slot_date,
        urgency=urgency,
    )

    # Tier 3 → broadcast includes the stop_calling cohort; we flag emergency=True
    # in score_candidates so the eligibility filter waives the fatigue gates.
    use_emergency_filter = next_tier == OutreachTier.TIER_3
    donor_pool = list(
        db.execute(select(Donor).where(Donor.is_active.is_(True))).scalars().all()
    )
    churn = get_churn_scores(donor_pool)
    survival = get_survival_scores(donor_pool)
    scored = score_candidates(
        slot, db=db, today=today,
        churn_scores=churn, survival_scores=survival,
        emergency=use_emergency_filter,
        donor_pool=donor_pool,
    )
    if not scored:
        return None

    # For Tier 2 expansion: skip donors already pinged in the expired wave
    if next_tier == OutreachTier.TIER_2:
        already_pinged = {p.donor_id for p in expired_wave.pings}
        scored = [c for c in scored if c.donor.id not in already_pinged]

    # Tier 3 broadcasts to the full pool (capped at 30 to avoid SMS bill blowout)
    max_batch = 30 if next_tier == OutreachTier.TIER_3 else slot.urgency.max_batch_size
    min_size = max(1, int(getattr(patient, "units_per_transfusion", 1) or 1))
    batch = minimal_batch(
        [c.donor for c in scored],
        churn_scores={c.donor.id: c.churn_90d for c in scored},
        target_p_accept=slot.urgency.target_p_accept,
        max_size=max_batch,
        min_size=min_size,
    )
    if not batch:
        return None

    rates = [
        adjusted_response_rate(d, {c.donor.id: c.churn_90d for c in scored}.get(d.id, 0.5))
        for d in batch
    ]
    realised = p_accept(rates)

    from app.outreach.engine import WaveAllocation  # self-ref, avoids re-import

    allocation = WaveAllocation(
        slot=slot,
        donors=batch,
        scored=scored,
        realised_p_accept=realised,
        target_p_accept=slot.urgency.target_p_accept,
        fully_covered=realised >= slot.urgency.target_p_accept,
    )
    new_wave = materialise_allocation(
        allocation, db=db, today=today,
        tier=next_tier,
        triggered_by=f"escalate_from_{expired_wave.id.hex[:8]}",
    )
    return new_wave
