"""Outreach scoring + eligibility + minimal-batch math.

Pure compute. No SQL writes, no side effects beyond reads. Everything callable
in tests with synthetic data.

Three groups of helpers:

    1.  ``p_accept`` / ``adjusted_response_rate`` / ``minimal_batch``
        ── the probability math behind batch sizing

    2.  ``urgency_for_patient`` / ``target_p_accept_for``
        ── translates ``days_until(next_transfusion)`` + per-patient cadence
           into one of the four urgency tiers (and the matching P_accept
           target)

    3.  ``is_eligible_for_outreach`` / ``composite_score``
        ── the per-candidate filter + ranker. Returns True/False and a float
           score the global allocator orders by.

Real-world signals consumed (all from the live DB):

    donor.blood_group, donor.kell_negative, patient.blood_group, patient.kell_negative
    donor.is_active, donor.last_donation_date            (90-day clinical deferral)
    donor.last_contacted_date                            (7-day social cooldown — NULL-safe)
    donor.total_calls, donor.calls_to_donations_ratio    (hard fatigue gates)
    donor.response_rate                                  (P_accept input)
    donor.lat/lng + patient.lat/lng                      (haversine for composite)
    OutreachCooldown rows                                (per-(donor, patient) cooldowns)
    OutreachPing rows in last 14d                        (fairness rotation penalty)
    BridgeMembership rows on other bridges               (bridge-stickiness penalty)

External callers fetch churn / survival predictions from the existing
``app.ml.churn`` + ``app.ml.survival`` predictors and pass the floats in —
the scorer stays decoupled from the ML stack so unit tests don't need to
load models.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.ml.utils import haversine_km
from app.models import (
    BridgeMembership,
    Donor,
    MembershipStatus,
    OutreachCooldown,
    OutreachPing,
    Patient,
    PingResponse,
    UrgencyTier,
)
from app.recommender.engine import _can_donate_to  # reuse — single source of truth


# ---------------------------------------------------------------------------
# 1.  Batch-size math — minimise pings subject to acceptance probability target
# ---------------------------------------------------------------------------

# Hard fatigue gate from the data audit: 29 donors in the real dataset have
# calls_to_donations_ratio > 10. Excluding them from normal outreach matches the
# `inactive_limited_despite_calls` cohort the churn model trained on, and gives
# us a deterministic backup signal when the ML model isn't loaded.
FATIGUE_CALLS_HARD_LIMIT = 10
FATIGUE_RATIO_HARD_LIMIT = 10.0

# Social cooldown defaults — overridable via cooldown rows
DEFAULT_CONTACT_COOLDOWN_DAYS = 7

# How far back we look at recent pings for the fairness rotation penalty.
FAIRNESS_WINDOW_DAYS = 14

# New-donor grace period — donors registered in the last 30 days shouldn't be
# pinged by the allocator. They haven't built a relationship with Blood Warriors
# yet; their first ask should be the scheduled cadence ping (rotation scheduler),
# not a stress outreach. Emergency mode bypasses this — life over manners.
NEW_DONOR_GRACE_DAYS = 30


def p_accept(adjusted_rates: Iterable[float]) -> float:
    """P(at least one donor in a batch accepts).

    Assuming independence across donors,

        P(accept) = 1 - Π_{i} (1 - r_i)

    where ``r_i`` is each donor's *adjusted* response rate (response_rate ×
    (1 - churn_90d) — see ``adjusted_response_rate``).

    Returns 0.0 for an empty batch.
    """
    p_none = 1.0
    n = 0
    for r in adjusted_rates:
        r_clipped = max(0.0, min(1.0, r))
        p_none *= (1.0 - r_clipped)
        n += 1
    if n == 0:
        return 0.0
    return 1.0 - p_none


def adjusted_response_rate(donor: Donor, churn_90d: float = 0.5) -> float:
    """Donor's response_rate down-weighted by current churn probability.

    A 90 %-historical responder predicted at 80 % churn isn't really an 80 %
    bet today — the churn model has seen something we haven't (long silence,
    missed calls, etc). Multiplying flattens the optimistic bias.
    """
    base = max(0.0, min(1.0, float(donor.response_rate or 0.0)))
    churn = max(0.0, min(1.0, float(churn_90d)))
    return base * (1.0 - churn)


def minimal_batch(
    ranked_candidates: list[Donor],
    *,
    churn_scores: Optional[dict[uuid.UUID, float]] = None,
    target_p_accept: float,
    max_size: int,
    min_size: int = 1,
) -> list[Donor]:
    """Smallest prefix of the candidate list whose P_accept ≥ target.

    Greedy: takes the top-ranked donor first, adds one at a time until both
    the target probability is met AND the batch is at least ``min_size``
    (or the cap is hit, or the pool is exhausted).

    ``min_size > 1`` is used for multi-unit transfusions
    (``patient.units_per_transfusion``) — if a patient needs 2 units, we
    actually need 2 donors to accept, not just 1, so the batch's target
    P_accept floor isn't enough on its own.

    Args:
        ranked_candidates: candidates already sorted by quality descending.
        churn_scores: map donor.id -> churn_90d in [0, 1]. Missing keys
            default to 0.5 (neutral).
        target_p_accept: stop once the realised P_accept clears this value.
        max_size: cap regardless of probability (anti-spam fail-safe).
        min_size: never return a batch shorter than this (multi-unit floor).
    """
    if churn_scores is None:
        churn_scores = {}

    batch: list[Donor] = []
    rates: list[float] = []
    for donor in ranked_candidates:
        if len(batch) >= max_size:
            break
        churn = churn_scores.get(donor.id, 0.5)
        rates.append(adjusted_response_rate(donor, churn))
        batch.append(donor)
        if len(batch) >= min_size and p_accept(rates) >= target_p_accept:
            return batch
    return batch  # may be < target if pool exhausted; caller decides whether to escalate


# ---------------------------------------------------------------------------
# 2.  Urgency tiering — variable per-patient cadence
# ---------------------------------------------------------------------------

# Dataset.csv shows transfusion cadence ranging 9–58 days (median 25). Using a
# fixed-hours-to-transfusion threshold for "urgent" would mis-classify both
# ends of that range. The ratio ``gap / cadence`` normalises across cadences.
URGENCY_CRITICAL_GAP_DAYS = 1
URGENCY_HIGH_GAP_DAYS = 3
URGENCY_HIGH_RATIO = 0.15
URGENCY_MEDIUM_GAP_DAYS = 7
URGENCY_MEDIUM_RATIO = 0.35


@dataclass(frozen=True)
class UrgencyContext:
    """Snapshot of how time-sensitive a slot is right now."""

    tier: UrgencyTier
    gap_days: int  # may be negative (overdue)
    cadence_days: int
    ratio: float  # gap / cadence, clipped to [0, 1]
    target_p_accept: float
    max_batch_size: int


# Per-tier P_accept targets and batch-size caps. These shape the cost-vs-coverage
# trade-off: critical patients get larger guarantees (more pings, more cost) and
# medium-cadence patients get cheaper waves.
URGENCY_PARAMS: dict[UrgencyTier, tuple[float, int]] = {
    UrgencyTier.CRITICAL: (0.95, 8),
    UrgencyTier.HIGH: (0.85, 6),
    UrgencyTier.MEDIUM: (0.70, 4),
    UrgencyTier.PLANNED: (0.0, 0),  # allocator skips PLANNED slots — rotation scheduler owns them
}


def target_p_accept_for(tier: UrgencyTier) -> float:
    return URGENCY_PARAMS[tier][0]


def max_batch_for(tier: UrgencyTier) -> int:
    return URGENCY_PARAMS[tier][1]


def urgency_for_patient(
    next_transfusion_date: date,
    cadence_days: int,
    *,
    today: date,
) -> UrgencyContext:
    """Classify the patient's next-transfusion slot into an urgency tier.

    Rules:

        CRITICAL — gap ≤ 1 day OR already overdue (gap < 0)
        HIGH     — gap ≤ 3 days AND gap / cadence ≤ 0.15
        MEDIUM   — gap ≤ 7 days AND gap / cadence ≤ 0.35
        PLANNED  — anything further out (rotation scheduler handles)
    """
    gap = (next_transfusion_date - today).days
    cad = max(1, int(cadence_days or 1))  # avoid /0 on missing/zero cadence
    ratio = max(0.0, min(1.0, gap / cad))

    if gap <= URGENCY_CRITICAL_GAP_DAYS:
        tier = UrgencyTier.CRITICAL
    elif gap <= URGENCY_HIGH_GAP_DAYS and ratio <= URGENCY_HIGH_RATIO:
        tier = UrgencyTier.HIGH
    elif gap <= URGENCY_MEDIUM_GAP_DAYS and ratio <= URGENCY_MEDIUM_RATIO:
        tier = UrgencyTier.MEDIUM
    else:
        tier = UrgencyTier.PLANNED

    return UrgencyContext(
        tier=tier,
        gap_days=gap,
        cadence_days=cad,
        ratio=ratio,
        target_p_accept=target_p_accept_for(tier),
        max_batch_size=max_batch_for(tier),
    )


# ---------------------------------------------------------------------------
# 3.  Eligibility + composite ranking
# ---------------------------------------------------------------------------


def precompute_active_cooldowns(
    db: Session, *, now: Optional[datetime] = None
) -> dict[tuple[uuid.UUID, Optional[uuid.UUID]], bool]:
    """One query returns ``{(donor_id, patient_id or None): True}`` for every
    cooldown that's currently active.

    Use ``cooldown_lookup_has_match(...)`` to query the resulting map.
    """
    now = now or datetime.utcnow()
    stmt = select(OutreachCooldown.donor_id, OutreachCooldown.patient_id).where(
        OutreachCooldown.expires_at > now
    )
    return {tuple(row): True for row in db.execute(stmt).all()}


def cooldown_lookup_has_match(
    cooldowns: dict[tuple[uuid.UUID, Optional[uuid.UUID]], bool],
    *,
    donor_id: uuid.UUID,
    patient_id: uuid.UUID,
) -> bool:
    """Match the precomputed cooldown table against a (donor, patient) pair.

    Global cooldowns ((donor_id, None)) match every patient; per-patient
    cooldowns match only the exact pair.
    """
    if (donor_id, None) in cooldowns:
        return True
    return (donor_id, patient_id) in cooldowns


def has_active_cooldown(
    db: Session,
    *,
    donor_id: uuid.UUID,
    patient_id: uuid.UUID,
    now: Optional[datetime] = None,
) -> bool:
    """True if any cooldown row covers this (donor, patient) pair right now.

    A row with ``patient_id IS NULL`` matches every patient (global cooldown).
    A row with the matching ``patient_id`` matches just that one (per-patient).
    Either kind blocks the donor.
    """
    now = now or datetime.utcnow()
    stmt = select(OutreachCooldown).where(
        and_(
            OutreachCooldown.donor_id == donor_id,
            OutreachCooldown.expires_at > now,
            or_(
                OutreachCooldown.patient_id.is_(None),
                OutreachCooldown.patient_id == patient_id,
            ),
        )
    )
    return db.execute(stmt).first() is not None


def _pings_in_last_window(
    db: Session,
    *,
    donor_id: uuid.UUID,
    window_days: int,
    now: Optional[datetime] = None,
) -> int:
    """How many outreach pings this donor received in the last N days.

    Powers the fairness rotation penalty so two equally-qualified donors get
    rotated rather than the same one always burning first.
    """
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=window_days)
    stmt = select(OutreachPing.id).where(
        and_(
            OutreachPing.donor_id == donor_id,
            OutreachPing.sent_at > cutoff,
        )
    )
    return len(db.execute(stmt).all())


def _is_in_another_active_bridge(
    db: Session, *, donor_id: uuid.UUID, exclude_bridge_id: Optional[uuid.UUID]
) -> bool:
    """True if the donor has an ACTIVE membership in any other bridge.

    Powers the bridge-stickiness penalty — don't opportunistically poach a
    donor away from a bridge they're committed to unless that bridge is
    actually over-supplied.
    """
    stmt = select(BridgeMembership.id).where(
        and_(
            BridgeMembership.donor_id == donor_id,
            BridgeMembership.status == MembershipStatus.ACTIVE,
        )
    )
    if exclude_bridge_id is not None:
        stmt = stmt.where(BridgeMembership.bridge_id != exclude_bridge_id)
    return db.execute(stmt).first() is not None


def is_eligible_for_outreach(
    donor: Donor,
    patient: Patient,
    *,
    today: date,
    db: Session,
    emergency: bool = False,
    bridge_id: Optional[uuid.UUID] = None,
    cooldown_lookup: Optional[dict[tuple[uuid.UUID, Optional[uuid.UUID]], bool]] = None,
) -> bool:
    """All-the-rules eligibility check for one (donor, patient) pair.

    Emergency mode waives social cooldowns + churn-class gate + total_calls
    fatigue gate. It NEVER waives:
        - Active status (Inactive donors stay out)
        - ABO/Rh compatibility (clinical safety)
        - 90-day post-donation deferral (clinical safety)
        - Kell phenotype match for repeat-transfused patients (alloimmunisation risk)
    """
    # ------- always-on clinical filters -------
    if not donor.is_active:
        return False

    # ABO/Rh compatibility — `unknown` blood group is already handled by
    # _can_donate_to (returns False)
    if not _can_donate_to(donor.blood_group, patient.blood_group):
        return False

    # 90-day clinical deferral after a previous donation (NEVER waived, even
    # in emergency tier — this is about donor health, not social cost)
    if donor.last_donation_date is not None:
        days_since = (today - donor.last_donation_date).days
        if days_since < 90:
            return False

    # Kell-negative patients (repeat-transfused) need Kell-negative donors
    # to minimise alloimmunisation
    if patient.kell_negative and not donor.kell_negative:
        return False

    if emergency:
        # In emergency tier we skip the social/behavioural gates below
        return True

    # ------- social cooldown — NULL-safe -------
    # If last_contacted_date is NULL (73 % of dataset) we treat the donor as
    # never-asked → no cooldown applies. Otherwise enforce 7-day window.
    if donor.last_contacted_date is not None:
        days_since_contact = (today - donor.last_contacted_date).days
        if days_since_contact < DEFAULT_CONTACT_COOLDOWN_DAYS:
            return False

    # Per-(donor, patient) cooldown rows — precomputed lookup if the caller
    # provided one, fall back to live query otherwise
    if cooldown_lookup is not None:
        if cooldown_lookup_has_match(
            cooldown_lookup, donor_id=donor.id, patient_id=patient.id
        ):
            return False
    elif has_active_cooldown(db, donor_id=donor.id, patient_id=patient.id):
        return False

    # ------- new-donor grace -------
    # Donors who just registered haven't built rapport yet — a cold "URGENT"
    # blast is the worst possible first interaction. BUT we only apply this
    # to donors we can VERIFY are actually new:
    #
    #   1. If they've donated before (total_donations > 0 or last_donation_date
    #      is not NULL), they're not new — skip the grace regardless of what
    #      ``registered_at`` says (the ingestion pipeline sets this to insert-time
    #      when the dataset's registration_date can't be parsed, which would
    #      otherwise mis-flag every donor as "registered today").
    #   2. Otherwise check ``registered_at`` — but only block if we have a
    #      genuine first-time donor + a recent registration date.
    has_donation_history = (
        (donor.total_donations or 0) > 0
        or donor.last_donation_date is not None
        or bool(donor.donated_earlier)
    )
    if not has_donation_history and donor.registered_at is not None:
        try:
            reg_date = donor.registered_at.date() if hasattr(donor.registered_at, "date") else donor.registered_at
            if (today - reg_date).days < NEW_DONOR_GRACE_DAYS:
                return False
        except (TypeError, AttributeError):
            pass

    # ------- fatigue gates (the data-derived ones) -------
    # 29 donors in the real Blood Warriors dataset have calls_to_donations_ratio
    # > 10 — they're the `inactive_limited_despite_calls` cohort. Hard-skip in
    # normal tiers; tier 3 + emergency may override by calling with emergency=True
    # or with the `inactive_limited_despite_calls` template branch.
    if (donor.total_calls or 0) > FATIGUE_CALLS_HARD_LIMIT:
        return False
    if (donor.calls_to_donations_ratio or 0.0) > FATIGUE_RATIO_HARD_LIMIT:
        return False

    return True


# Composite scoring — extends the existing recommender's score with three
# new signals. Keep all weights summing to 1.0 (plus separate penalties).
W_DISTANCE = 0.30
W_RESPONSE = 0.30
W_CHURN = 0.40
W_KELL_BONUS = 0.10
W_SURVIVAL_BONUS = 0.05
W_ROTATION_PENALTY = 0.10
W_BRIDGE_STICKINESS_PENALTY = 0.15

# Distance reaches the half-mark at ~25 km — empirical: most Bridge donations
# happen within 30 km of the hospital.
DISTANCE_HALF_LIFE_KM = 25.0


def _distance_factor(distance_km: float) -> float:
    """Maps distance to a [0, 1] factor — closer = higher."""
    if distance_km < 0:
        return 0.0
    # Exponential decay: at 25 km factor=0.5; at 0 km factor=1; at 100 km ~0.06
    import math
    return math.exp(-distance_km / DISTANCE_HALF_LIFE_KM)


def precompute_recent_ping_counts(
    db: Session,
    *,
    window_days: int = FAIRNESS_WINDOW_DAYS,
    now: Optional[datetime] = None,
) -> dict[uuid.UUID, int]:
    """One query returns ``donor_id -> count(pings in last N days)``.

    Used by the allocator to avoid the N+1 per-donor query inside
    ``composite_score``. With 6,949 donors and 79 patients in a real cycle,
    skipping this turns the cycle from minutes into milliseconds.
    """
    from sqlalchemy import func as sa_func

    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=window_days)
    stmt = (
        select(OutreachPing.donor_id, sa_func.count(OutreachPing.id))
        .where(OutreachPing.sent_at > cutoff)
        .group_by(OutreachPing.donor_id)
    )
    rows = db.execute(stmt).all()
    return {donor_id: int(count) for donor_id, count in rows}


def precompute_active_bridge_memberships(
    db: Session,
) -> dict[uuid.UUID, set[uuid.UUID]]:
    """One query returns ``donor_id -> {bridge_id, ...}`` for ACTIVE memberships.

    The allocator uses this for the bridge-stickiness penalty.
    """
    stmt = select(BridgeMembership.donor_id, BridgeMembership.bridge_id).where(
        BridgeMembership.status == MembershipStatus.ACTIVE
    )
    out: dict[uuid.UUID, set[uuid.UUID]] = {}
    for donor_id, bridge_id in db.execute(stmt).all():
        out.setdefault(donor_id, set()).add(bridge_id)
    return out


def composite_score(
    donor: Donor,
    patient: Patient,
    *,
    db: Session,
    churn_90d: float = 0.5,
    survival_30d: float = 0.5,
    today: Optional[date] = None,
    bridge_id: Optional[uuid.UUID] = None,
    # ---- per-cycle precomputed caches (optional, for perf) ----
    recent_ping_counts: Optional[dict[uuid.UUID, int]] = None,
    active_bridge_memberships: Optional[dict[uuid.UUID, set[uuid.UUID]]] = None,
) -> float:
    """Rank-quality of this donor for this patient, on [-∞, +∞].

    Higher is better. The global allocator sorts each patient's candidate
    pool by this score and feeds the top of the list into ``minimal_batch``.

    Per-cycle the engine pre-fills ``recent_ping_counts`` and
    ``active_bridge_memberships`` with one SQL query each, then passes them
    through every per-donor call → no N+1 problem. When the caches are
    omitted (tests, ad-hoc callers) the function falls back to per-call
    DB queries — slower but functionally identical.
    """
    today = today or date.today()

    # Distance
    distance_km = haversine_km(donor.lat, donor.lng, patient.lat, patient.lng)
    distance = _distance_factor(distance_km)

    # Composite base — same shape as app.recommender.engine._score_candidate
    response = max(0.0, min(1.0, float(donor.response_rate or 0.0)))
    churn_inverse = 1.0 - max(0.0, min(1.0, float(churn_90d)))

    base = (
        W_DISTANCE * distance
        + W_RESPONSE * response
        + W_CHURN * churn_inverse
    )
    if patient.kell_negative and donor.kell_negative:
        base += W_KELL_BONUS

    # Survival bonus — small weight, prefer donors who'll still be around
    base += W_SURVIVAL_BONUS * max(0.0, min(1.0, float(survival_30d)))

    # Fairness rotation penalty — capped so a busy donor isn't permanently locked out
    if recent_ping_counts is not None:
        recent_pings = recent_ping_counts.get(donor.id, 0)
    else:
        recent_pings = _pings_in_last_window(
            db, donor_id=donor.id, window_days=FAIRNESS_WINDOW_DAYS
        )
    rotation_pen = min(W_ROTATION_PENALTY, recent_pings / 50.0)
    base -= rotation_pen

    # Bridge stickiness — if they're active in some OTHER bridge, prefer
    # leaving them there
    if active_bridge_memberships is not None:
        other_bridges = active_bridge_memberships.get(donor.id, set())
        is_sticky = any(bid != bridge_id for bid in other_bridges)
    else:
        is_sticky = _is_in_another_active_bridge(
            db, donor_id=donor.id, exclude_bridge_id=bridge_id
        )
    if is_sticky:
        base -= W_BRIDGE_STICKINESS_PENALTY

    return base
