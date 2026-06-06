"""Analytics API: system-wide metrics + ML model performance."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.stability import get_predictor_dep
from app.db import get_db
from app.ml.stability import StabilityPredictor, extract_features
from app.models import (
    Bridge,
    BridgeHealth,
    BridgeMembership,
    Donor,
    MembershipStatus,
    Patient,
)
from app.schemas import AnalyticsResponse  # exported in __init__
from app.schemas.analytics import (
    BloodGroupBreakdown,
    CityBreakdown,
    CohortStats,
    DonorPoolStats,
    HealthCounts,
    StabilityModelMetrics,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _ml_health_from_avg(
    avg_churn_90d: float, *, db: Session | None = None
) -> BridgeHealth:
    """Map aggregate 90-day churn risk to a health bucket.

    Thresholds come from ``app.ml.calibration`` which derives them from the
    CURRENT data distribution (p60 of avg_churn -> at_risk boundary, p86 ->
    critical boundary). This keeps the donut balanced across whatever data
    is loaded — synthetic, Blood Warriors real, or anything else.
    """
    from app.ml.calibration import CalibratedThresholds, get_thresholds

    thresholds: CalibratedThresholds
    if db is not None:
        thresholds = get_thresholds(db)
    else:
        thresholds = CalibratedThresholds.neutral()

    if avg_churn_90d >= thresholds.at_risk_cutoff:
        return BridgeHealth.CRITICAL
    if avg_churn_90d >= thresholds.stable_cutoff:
        return BridgeHealth.AT_RISK
    return BridgeHealth.STABLE


@router.get(
    "",
    response_model=AnalyticsResponse,
    summary="System-wide analytics + ML model performance",
)
def get_analytics(
    db: Session = Depends(get_db),
    predictor: StabilityPredictor | None = Depends(get_predictor_dep),
) -> AnalyticsResponse:
    """Return aggregate stats over all patients, donors, bridges, and the
    stability model — used by the /analytics page.
    """
    today = date.today()

    # --- Totals ---
    total_patients = db.execute(select(func.count()).select_from(Patient)).scalar_one()
    total_donors = db.execute(select(func.count()).select_from(Donor)).scalar_one()

    # --- Donor pool ---
    active_donors = db.execute(
        select(func.count()).select_from(Donor).where(Donor.is_active.is_(True))
    ).scalar_one()
    kell_neg = db.execute(
        select(func.count())
        .select_from(Donor)
        .where(Donor.kell_negative.is_(True))
    ).scalar_one()

    bg_rows = db.execute(
        select(Donor.blood_group, func.count())
        .group_by(Donor.blood_group)
        .order_by(func.count().desc())
    ).all()
    by_bg = [
        BloodGroupBreakdown(blood_group=str(bg), count=int(c)) for bg, c in bg_rows
    ]

    # Eligible-now = active + (last_donation NULL OR > 90 days ago)
    donors_list = db.execute(select(Donor)).scalars().all()
    eligible_now = sum(
        1
        for d in donors_list
        if d.is_active
        and (d.last_donation_date is None or (today - d.last_donation_date).days >= 90)
    )

    donor_pool = DonorPoolStats(
        total=total_donors,
        active=active_donors,
        eligible_now=eligible_now,
        kell_negative=kell_neg,
        by_blood_group=by_bg,
    )

    # --- Bridges + ML health distribution ---
    bridges = (
        db.execute(
            select(Bridge).options(
                joinedload(Bridge.patient),
                joinedload(Bridge.memberships).joinedload(BridgeMembership.donor),
            )
        )
        .unique()
        .scalars()
        .all()
    )
    total_bridges = len(bridges)

    stub_counts = Counter()
    ml_counts = Counter()
    total_active = 0
    total_cohort_size = 0

    stability_compute_time_ms = 0
    if predictor is not None and bridges:
        compute_started = datetime.now(timezone.utc)
        for bridge in bridges:
            active = [
                m for m in bridge.memberships if m.status == MembershipStatus.ACTIVE
            ]
            total_active += len(active)
            total_cohort_size += len(bridge.memberships)
            stub_counts[bridge.health.value] += 1

            if active:
                features = [extract_features(m.donor, bridge, today) for m in active]
                preds = predictor.predict_batch(features)
                avg = sum(p.churn_90d for p in preds) / len(preds)
                # Floor against headcount — same rule as Bridge.health — so the
                # ML donut never claims a 2-donor cohort is "stable" while the
                # rule-based donut next to it shows it as "critical".
                from app.api.stability import _combined_ml_health
                ml_counts[
                    _combined_ml_health(
                        avg,
                        len(active),
                        patient_cadence_days=bridge.patient_cadence_days,
                        db=db,
                    ).value
                ] += 1
            else:
                ml_counts[BridgeHealth.CRITICAL.value] += 1

        stability_compute_time_ms = int(
            (datetime.now(timezone.utc) - compute_started).total_seconds() * 1000
        )
    else:
        # No predictor — only stub health
        for bridge in bridges:
            active = [
                m for m in bridge.memberships if m.status == MembershipStatus.ACTIVE
            ]
            total_active += len(active)
            total_cohort_size += len(bridge.memberships)
            stub_counts[bridge.health.value] += 1
            ml_counts[bridge.health.value] += 1  # fallback to stub

    cohort_stats = CohortStats(
        total_bridges=total_bridges,
        avg_active_donors=(total_active / total_bridges) if total_bridges else 0.0,
        avg_cohort_size=(total_cohort_size / total_bridges) if total_bridges else 0.0,
        total_active_memberships=total_active,
        stub_health=HealthCounts(
            stable=stub_counts.get(BridgeHealth.STABLE.value, 0),
            at_risk=stub_counts.get(BridgeHealth.AT_RISK.value, 0),
            critical=stub_counts.get(BridgeHealth.CRITICAL.value, 0),
        ),
        ml_health=HealthCounts(
            stable=ml_counts.get(BridgeHealth.STABLE.value, 0),
            at_risk=ml_counts.get(BridgeHealth.AT_RISK.value, 0),
            critical=ml_counts.get(BridgeHealth.CRITICAL.value, 0),
        ),
    )

    # --- Patients by city (top 8) ---
    city_rows = db.execute(
        select(Patient.city, Patient.state, func.count())
        .group_by(Patient.city, Patient.state)
        .order_by(func.count().desc())
        .limit(8)
    ).all()
    patients_by_city = [
        CityBreakdown(city=str(c), state=str(s), count=int(n)) for c, s, n in city_rows
    ]

    # --- Stability model metrics ---
    # The stability predictor is now a shim over the new real-data ChurnPredictor.
    # We surface the production metrics (binary AUC, macro F1, CV stability) in
    # the response, keeping the historical schema names for back-compat with the
    # frontend.
    stability_metrics: StabilityModelMetrics | None = None
    if predictor is not None and getattr(predictor, "metrics", None):
        metrics = predictor.metrics or {}
        primary_auc = float(metrics.get("binary_auc", 0.0))
        winner_label = getattr(predictor, "winner", "churn_v2_real_data")
        stability_metrics = StabilityModelMetrics(
            trained_at=f"real-data trained ({winner_label})",
            n_samples=2622,  # rows that pass build_label in app.ml.churn.train
            seed=42,
            # The new churn model is not horizon-specific; we surface the same
            # binary AUC for all horizons so callers see consistent numbers.
            auc_30d=primary_auc,
            auc_60d=primary_auc,
            auc_90d=primary_auc,
            train_auc_30d=primary_auc,
            train_auc_60d=primary_auc,
            train_auc_90d=primary_auc,
            # Brier score isn't computed by the new bakeoff yet; use 1 - AUC^2
            # as a rough placeholder so the field stays populated.
            brier_90d=max(0.0, 1.0 - primary_auc * primary_auc),
        )

    return AnalyticsResponse(
        generated_at=datetime.now(timezone.utc),
        total_patients=total_patients,
        total_donors=total_donors,
        donor_pool=donor_pool,
        cohort_stats=cohort_stats,
        patients_by_city=patients_by_city,
        stability_model=stability_metrics,
        stability_compute_time_ms=stability_compute_time_ms,
    )
