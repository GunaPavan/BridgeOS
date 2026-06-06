"""ML predictions API: real-data churn + survival per donor + bake-off reports.

Exposes the trained models (app.ml.churn + app.ml.survival):

    GET /donors/{donor_id}/churn-prediction
        → multi-class disengagement probability + recommended intervention
    GET /donors/{donor_id}/survival
        → time-to-disengagement curve (90d / 180d / 365d survival probability)
    GET /ml/model-metrics
        → training metrics for both models (for /analytics dashboard)
    GET /ml/bakeoff/{model_name}
        → full algorithm comparison table from the bake-off (churn|survival)

These endpoints run the trained models on demand. Cold-start: ~30ms (model
load). Steady-state: ~5ms per prediction. Real-time enough for any UX.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.ml.churn import load_predictor as load_churn_predictor
from app.ml.survival import load_predictor as load_survival_predictor
from app.models import Donor


router = APIRouter(tags=["ml-predictions"])


# Resolve from project root (4 levels up: ml_predictions.py -> api -> app -> backend -> root)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_bakeoff_report(model_name: str) -> list[dict] | None:
    """Load bake-off JSON written by either bakeoff trainer."""
    report_path = _PROJECT_ROOT / "models" / model_name / "bakeoff_report.json"
    if not report_path.exists():
        return None
    try:
        with open(report_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


@router.get(
    "/donors/{donor_id}/churn-prediction",
    summary="Multi-class churn classification for a single donor",
)
def predict_donor_churn(donor_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Run the multi-class churn model and return per-class probabilities
    plus the recommended coordinator action.

    Returns 503 if the model isn't trained yet (run
    `python -m app.ml.churn.train` and restart).
    """
    donor = db.get(Donor, donor_id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Donor {donor_id} not found",
        )
    predictor = load_churn_predictor()
    if predictor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Churn model not loaded. Train with "
                "`python -m app.ml.churn.train` and restart."
            ),
        )
    prediction = predictor.predict(donor)
    return {
        "donor_id": str(donor.id),
        "donor_name": donor.name,
        "model_winner": predictor.winner,
        "model_metrics": predictor.metrics,
        **prediction.as_dict(),
    }


@router.get(
    "/donors/{donor_id}/survival",
    summary="Time-to-event survival curve for one donor",
)
def predict_donor_survival(donor_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Return survival probability at 90 / 180 / 365 days from the model's
    time origin, plus a risk score for prioritization."""
    donor = db.get(Donor, donor_id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Donor {donor_id} not found",
        )
    predictor = load_survival_predictor()
    if predictor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Survival model not loaded. Train with "
                "`python -m app.ml.survival.bakeoff` and restart."
            ),
        )
    prediction = predictor.predict(donor)
    return {
        "donor_id": str(donor.id),
        "donor_name": donor.name,
        "model_winner": predictor.winner,
        "model_metrics": predictor.metrics,
        **prediction.as_dict(),
    }


@router.get(
    "/ml/model-metrics",
    summary="Training metrics for both production ML models",
)
def get_model_metrics() -> dict:
    """Surface the AUC / C-index / cross-validation scores so the analytics
    dashboard can display them. If a model isn't loaded, its slot is null."""
    churn = load_churn_predictor()
    survival = load_survival_predictor()
    return {
        "churn": {
            "loaded": churn is not None,
            "winner": churn.winner if churn else None,
            "metrics": churn.metrics if churn else None,
            "feature_names": churn.feature_names if churn else None,
        },
        "survival": {
            "loaded": survival is not None,
            "winner": survival.winner if survival else None,
            "metrics": survival.metrics if survival else None,
            "feature_names": survival.feature_names if survival else None,
        },
    }


@router.get(
    "/ml/donor-pool-insights",
    summary="Network-wide ML-driven analytics on the entire donor population",
)
def get_donor_pool_insights(db: Session = Depends(get_db)) -> dict:
    """Score every active donor through both models and aggregate. Powers the
    /analytics ML insights panel — class distribution + survival quartiles +
    high-intervention counts.

    Cap at 500 donors per call to keep latency under 300 ms even on a small
    instance. The /analytics page samples; not used for operational decisions.
    """
    churn = load_churn_predictor()
    survival = load_survival_predictor()
    if churn is None or survival is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Both churn + survival models must be loaded.",
        )

    from sqlalchemy import select as _select
    from app.models import Donor as _Donor

    donors = db.execute(_select(_Donor).limit(500)).scalars().all()
    if not donors:
        return {
            "n_scored": 0,
            "predicted_class_counts": {},
            "p_active_mean": 0.0,
            "high_risk_count": 0,
            "low_risk_count": 0,
            "survival_365d_median": 0.0,
            "survival_365d_p25": 0.0,
            "survival_365d_p75": 0.0,
            "needs_reminder_count": 0,
            "stop_calling_count": 0,
        }

    churn_preds = churn.predict_batch(donors)
    surv_preds = survival.predict_batch(donors)

    # Aggregate
    class_counts: dict[str, int] = {}
    p_active_sum = 0.0
    high_risk = 0      # p_active < 0.3
    low_risk = 0       # p_active >= 0.7
    needs_reminder = 0       # predicted Not Donated 1Y
    stop_calling = 0         # predicted Limited Despite Calls
    survival_365 = []

    for cp in churn_preds:
        class_counts[cp.predicted_class] = class_counts.get(cp.predicted_class, 0) + 1
        p_active_sum += cp.p_active
        if cp.p_active < 0.3:
            high_risk += 1
        if cp.p_active >= 0.7:
            low_risk += 1
        if cp.predicted_class == "inactive_not_donated_1y":
            needs_reminder += 1
        elif cp.predicted_class == "inactive_limited_despite_calls":
            stop_calling += 1

    for sp in surv_preds:
        survival_365.append(sp.p_survive_365d)

    survival_365.sort()
    n = len(survival_365)
    def _pct(p: float) -> float:
        if n == 0:
            return 0.0
        idx = max(0, min(n - 1, int(p * n)))
        return survival_365[idx]

    return {
        "n_scored": n,
        "predicted_class_counts": class_counts,
        "p_active_mean": round(p_active_sum / n, 4) if n else 0.0,
        "high_risk_count": high_risk,
        "low_risk_count": low_risk,
        "survival_365d_median": round(_pct(0.5), 4),
        "survival_365d_p25": round(_pct(0.25), 4),
        "survival_365d_p75": round(_pct(0.75), 4),
        "needs_reminder_count": needs_reminder,
        "stop_calling_count": stop_calling,
        "churn_winner": churn.winner,
        "survival_winner": survival.winner,
    }


@router.get(
    "/ml/bakeoff/{model_name}",
    summary="Bake-off comparison of all algorithms tested for a given model",
)
def get_bakeoff_report(model_name: Literal["churn", "survival"]) -> dict:
    """Return the full bake-off comparison table for the named model.

    The report contains all algorithms tested, with their CV/test metrics
    and inference latency — used by the /analytics page to show the
    rationale behind why the winner was picked.
    """
    report = _load_bakeoff_report(model_name)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No bake-off report found for '{model_name}'. Train with "
                f"`python -m app.ml.{model_name}.bakeoff` first."
            ),
        )
    # Determine winner (top by relevant metric)
    if model_name == "churn":
        # Sort by CV macro F1 desc, with test F1 + AUC as tie breakers
        sorted_rows = sorted(
            report,
            key=lambda r: (
                -r.get("cv_macro_f1_mean", 0.0),
                -r.get("test_macro_f1", 0.0),
                -r.get("test_binary_auc", 0.0),
            ),
        )
    else:
        sorted_rows = sorted(
            [r for r in report if not r.get("failed")],
            key=lambda r: -r.get("c_index_test", 0.0),
        )
    winner = sorted_rows[0] if sorted_rows else None
    return {
        "model_name": model_name,
        "winner": winner["name"] if winner else None,
        "n_algorithms_tested": len(report),
        "rows": report,
    }
