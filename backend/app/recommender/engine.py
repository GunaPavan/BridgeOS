"""Pure-function recommender that combines stability + matching.

Inputs: a Bridge (with patient + cohort loaded), the donor pool, today, and a
StabilityPredictor. Outputs: weak donors in the bridge + ranked replacement
candidates with plain-language rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.ml.scheduler.solver import DEFERRAL_DAYS
from app.ml.stability import Factor, StabilityPredictor, extract_features
from app.models import (
    BloodGroup,
    Bridge,
    BridgeMembership,
    Donor,
    MembershipStatus,
    Patient,
)
from app.ml.utils import haversine_km

# Default threshold for flagging an individual donor as "weak" — used ONLY
# when no DB is passed to the recommender. Production calls always pass the
# session, which triggers calibration against the live distribution (p70 of
# per-donor churn_90d on currently loaded data). See app/ml/calibration.py.
#
# This constant is kept as a fallback for unit tests that exercise pure-logic
# helpers without a session. It is NOT a "production threshold."
AT_RISK_CHURN_THRESHOLD = 0.70

# Composite-score weights (sum to 1.0)
W_DISTANCE = 0.30
W_RESPONSE = 0.30
W_CHURN = 0.40

# Phenotype bonus added on top of composite (boosts to top of list)
KELL_MATCH_BONUS = 0.10


# --- Blood-group compatibility (donor -> recipient) ---
_DONOR_TO_RECIPIENTS: dict[BloodGroup, set[BloodGroup]] = {
    BloodGroup.O_NEG: set(BloodGroup),
    BloodGroup.O_POS: {BloodGroup.O_POS, BloodGroup.A_POS, BloodGroup.B_POS, BloodGroup.AB_POS},
    BloodGroup.A_NEG: {BloodGroup.A_NEG, BloodGroup.A_POS, BloodGroup.AB_NEG, BloodGroup.AB_POS},
    BloodGroup.A_POS: {BloodGroup.A_POS, BloodGroup.AB_POS},
    BloodGroup.B_NEG: {BloodGroup.B_NEG, BloodGroup.B_POS, BloodGroup.AB_NEG, BloodGroup.AB_POS},
    BloodGroup.B_POS: {BloodGroup.B_POS, BloodGroup.AB_POS},
    BloodGroup.AB_NEG: {BloodGroup.AB_NEG, BloodGroup.AB_POS},
    BloodGroup.AB_POS: {BloodGroup.AB_POS},
}


def _can_donate_to(donor_bg: BloodGroup, recipient_bg: BloodGroup) -> bool:
    """Return True iff donor_bg can clinically donate to recipient_bg.

    The real Blood Warriors dataset has ~5% of donors with blood_group set to
    ``unknown`` (no group on file). Unknown on either side is conservatively
    treated as incompatible — we can't recruit a donor whose group we don't
    know, and we can't match against a patient whose group is missing.
    """
    allowed = _DONOR_TO_RECIPIENTS.get(donor_bg)
    if allowed is None:
        return False
    return recipient_bg in allowed


@dataclass(frozen=True)
class CandidateRationale:
    factor: str
    value: float
    description: str


@dataclass(frozen=True)
class Candidate:
    donor: Donor
    composite_score: float  # 0..1, higher = better
    distance_km: float
    predicted_churn_90d: float
    days_until_eligible: int  # 0 if already eligible
    rationale: list[CandidateRationale]


@dataclass(frozen=True)
class WeakDonor:
    membership: BridgeMembership
    churn_90d: float
    top_factors: list[Factor]


@dataclass(frozen=True)
class BridgeRecommendation:
    bridge: Bridge
    weak_donors: list[WeakDonor]
    candidates: list[Candidate]
    urgency: str  # "critical" | "high" | "medium"


def _days_until_eligible(donor: Donor, today: date) -> int:
    if donor.last_donation_date is None:
        return 0
    gap = (today - donor.last_donation_date).days
    return max(0, DEFERRAL_DAYS - gap)


def _score_candidate(
    donor: Donor,
    patient: Patient,
    predicted_churn_90d: float,
    distance_km: float,
) -> float:
    """Composite score in [0, 1]. Higher is better."""
    # Cost components — each in [0, 1], lower is better
    dist_cost = min(distance_km / 50.0, 1.0)
    resp_cost = 1.0 - float(donor.response_rate)
    churn_cost = predicted_churn_90d

    cost = (
        W_DISTANCE * dist_cost
        + W_RESPONSE * resp_cost
        + W_CHURN * churn_cost
    )
    score = max(0.0, 1.0 - cost)

    # Bonuses (additive after the cost)
    if patient.kell_negative and donor.kell_negative:
        score = min(1.0, score + KELL_MATCH_BONUS)
    return score


def _rationale(
    donor: Donor,
    patient: Patient,
    distance_km: float,
    predicted_churn_90d: float,
    days_until_eligible: int,
) -> list[CandidateRationale]:
    items: list[CandidateRationale] = [
        CandidateRationale(
            factor="distance_km",
            value=distance_km,
            description=f"{distance_km:.1f} km from {patient.hospital}",
        ),
        CandidateRationale(
            factor="response_rate",
            value=float(donor.response_rate),
            description=f"{int(donor.response_rate * 100)}% historical response rate",
        ),
        CandidateRationale(
            factor="predicted_churn_90d",
            value=predicted_churn_90d,
            description=f"{int(predicted_churn_90d * 100)}% predicted 90-day churn",
        ),
    ]
    if patient.kell_negative and donor.kell_negative:
        items.append(
            CandidateRationale(
                factor="kell_match",
                value=1.0,
                description="Kell-negative match — preferred for repeat-transfused patient",
            )
        )
    if days_until_eligible == 0:
        items.append(
            CandidateRationale(
                factor="eligibility",
                value=0.0,
                description="Eligible to donate now",
            )
        )
    else:
        items.append(
            CandidateRationale(
                factor="eligibility",
                value=float(days_until_eligible),
                description=f"Eligible in {days_until_eligible} days",
            )
        )
    return items


def compute_recommendations_for_bridge(
    bridge: Bridge,
    candidate_pool: Iterable[Donor],
    predictor: StabilityPredictor,
    today: date,
    *,
    top_k: int = 5,
    at_risk_threshold: float | None = None,
    db: Session | None = None,
    prediction_cache: dict | None = None,
) -> BridgeRecommendation:
    """Compute weak donors + ranked replacement candidates for one bridge.

    When `at_risk_threshold` is None and `db` is given, the threshold is
    calibrated against the live data distribution. Otherwise it falls back
    to the AT_RISK_CHURN_THRESHOLD constant (for unit-test convenience).

    ``prediction_cache`` (donor.id -> StabilityPrediction) lets callers reuse
    predictions across many bridges — the stability model is donor-only, not
    bridge-specific, so the same prediction is valid for every bridge it
    appears in. ``list_bridges_with_recommendations`` builds this cache once
    over the full pool, dropping a 79×6949 inner loop to a single 6949 batch.
    """
    patient = bridge.patient

    if at_risk_threshold is None:
        if db is not None:
            from app.ml.calibration import get_thresholds
            at_risk_threshold = get_thresholds(db).at_risk_donor
        else:
            at_risk_threshold = AT_RISK_CHURN_THRESHOLD

    def _predict_many(donors: list[Donor]) -> list:
        """Use the cache when available; otherwise predict on the spot."""
        if prediction_cache is None:
            return predictor.predict_batch(
                [extract_features(d, bridge, today) for d in donors]
            )
        missing = [d for d in donors if d.id not in prediction_cache]
        if missing:
            new_preds = predictor.predict_batch(
                [extract_features(d, bridge, today) for d in missing]
            )
            for d, p in zip(missing, new_preds):
                prediction_cache[d.id] = p
        return [prediction_cache[d.id] for d in donors]

    # 1) Identify weak donors via the stability model
    active_members = [m for m in bridge.memberships if m.status == MembershipStatus.ACTIVE]
    member_predictions = _predict_many([m.donor for m in active_members]) if active_members else []

    weak_donors: list[WeakDonor] = []
    for m, pred in zip(active_members, member_predictions):
        if pred.churn_90d >= at_risk_threshold:
            weak_donors.append(
                WeakDonor(
                    membership=m,
                    churn_90d=pred.churn_90d,
                    top_factors=pred.top_factors,
                )
            )
    weak_donors.sort(key=lambda w: w.churn_90d, reverse=True)

    # 2) Compute candidates regardless of weak donors (so the inbox can still
    # show "strengthen the cohort" suggestions even when nobody is critical)
    current_member_ids = {m.donor_id for m in active_members}
    eligible_candidates = [
        d
        for d in candidate_pool
        if d.id not in current_member_ids
        and d.is_active
        and _can_donate_to(d.blood_group, patient.blood_group)
        and (not patient.kell_negative or d.kell_negative)
    ]

    if not eligible_candidates:
        urgency = _urgency_label(weak_donors, db=db)
        return BridgeRecommendation(
            bridge=bridge,
            weak_donors=weak_donors,
            candidates=[],
            urgency=urgency,
        )

    candidate_predictions = _predict_many(eligible_candidates)

    scored: list[Candidate] = []
    for donor, pred in zip(eligible_candidates, candidate_predictions):
        distance = haversine_km(donor.lat, donor.lng, patient.lat, patient.lng)
        score = _score_candidate(donor, patient, pred.churn_90d, distance)
        scored.append(
            Candidate(
                donor=donor,
                composite_score=score,
                distance_km=distance,
                predicted_churn_90d=pred.churn_90d,
                days_until_eligible=_days_until_eligible(donor, today),
                rationale=_rationale(
                    donor, patient, distance, pred.churn_90d, _days_until_eligible(donor, today)
                ),
            )
        )

    scored.sort(key=lambda c: c.composite_score, reverse=True)
    top = scored[:top_k]

    return BridgeRecommendation(
        bridge=bridge,
        weak_donors=weak_donors,
        candidates=top,
        urgency=_urgency_label(weak_donors, db=db),
    )


def _urgency_label(
    weak_donors: list[WeakDonor], *, db: Session | None = None
) -> str:
    """Bucket a bridge into critical / high / medium urgency.

    Top-risk percentile cutoffs come from ``app.ml.calibration`` so the
    inbox stays balanced as the data distribution shifts (synthetic ->
    real Blood Warriors data, ingest cycles, etc.). Count thresholds
    (4+ critical, 3+ high) stay ordinal — they don't depend on the
    distribution shape.
    """
    if not weak_donors:
        return "medium"

    from app.ml.calibration import CalibratedThresholds, get_thresholds

    thresholds: CalibratedThresholds
    if db is not None:
        thresholds = get_thresholds(db)
    else:
        thresholds = CalibratedThresholds.neutral()

    top_risk = max(w.churn_90d for w in weak_donors)
    if (
        top_risk >= thresholds.urgency_critical_top
        or len(weak_donors) >= thresholds.urgency_critical_count
    ):
        return "critical"
    if (
        top_risk >= thresholds.urgency_high_top
        or len(weak_donors) >= thresholds.urgency_high_count
    ):
        return "high"
    return "medium"


def list_bridges_with_recommendations(
    db: Session,
    predictor: StabilityPredictor,
    today: date,
    *,
    only_weak: bool = True,
    top_k_per_bridge: int = 5,
    at_risk_threshold: float | None = None,
) -> list[BridgeRecommendation]:
    """Compute recommendations for every active bridge in the DB.

    If `only_weak=True`, only bridges with at least one at-risk donor are returned.
    When ``at_risk_threshold`` is None, the threshold is calibrated against
    the current data distribution via app.ml.calibration.
    """
    if at_risk_threshold is None:
        from app.ml.calibration import get_thresholds
        at_risk_threshold = get_thresholds(db).at_risk_donor
    bridges_stmt = (
        select(Bridge)
        .options(
            joinedload(Bridge.patient),
            joinedload(Bridge.memberships).joinedload(BridgeMembership.donor),
        )
    )
    bridges = db.execute(bridges_stmt).unique().scalars().all()

    # Single donor pool query (eagerly loaded with memberships for feature extraction)
    donor_stmt = (
        select(Donor)
        .options(joinedload(Donor.memberships))
    )
    donor_pool = list(db.execute(donor_stmt).unique().scalars().all())

    # Warm the prediction cache against the FULL donor pool in one batch.
    # extract_features is donor-only (the bridge arg is ignored by the
    # compat shim), so the same prediction is valid for every bridge.
    prediction_cache: dict = {}
    warm_preds = predictor.predict_batch(
        [extract_features(d, None, today) for d in donor_pool]
    )
    for d, p in zip(donor_pool, warm_preds):
        prediction_cache[d.id] = p

    out: list[BridgeRecommendation] = []
    for bridge in bridges:
        rec = compute_recommendations_for_bridge(
            bridge=bridge,
            candidate_pool=donor_pool,
            predictor=predictor,
            today=today,
            top_k=top_k_per_bridge,
            at_risk_threshold=at_risk_threshold,
            db=db,
            prediction_cache=prediction_cache,
        )
        if only_weak and not rec.weak_donors:
            continue
        out.append(rec)

    # Sort: critical first, then high, then medium; within each, by max churn desc
    urgency_rank = {"critical": 0, "high": 1, "medium": 2}
    out.sort(
        key=lambda r: (
            urgency_rank[r.urgency],
            -max((w.churn_90d for w in r.weak_donors), default=0.0),
        )
    )
    return out
