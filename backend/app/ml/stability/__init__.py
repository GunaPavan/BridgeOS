"""Stability predictor — compatibility shim.

⚠️ HISTORICAL NOTE
   This module previously held a procedurally-trained XGBoost model
   (synthetic training data with hand-crafted log-hazard coefficients). That
   model is GONE — synthetic data has no business in a system designed for
   real Blood Warriors operations.

✅ TODAY
   `StabilityPredictor` is now a thin adapter that routes to the
   real-data-trained `app.ml.churn.ChurnPredictor` (XGBoost trained on
   2,622 labeled Blood Warriors donors, AUC 0.979 / macro F1 0.810).

   Callers continue to use the same API (`predictor.predict_batch(features)`,
   `prediction.churn_90d`, `prediction.top_factors`) without changes. Under
   the hood every call hits the new model.

Mapping:
    churn_90d  := 1 − p_active           (prob of being in any inactive class)
    churn_60d  := churn_90d × 0.85       (decay approximation; new model is
    churn_30d  := churn_90d × 0.60        not horizon-specific by design)

For the *honest* per-horizon answer use the survival model:
    from app.ml.survival import load_predictor
    predictor.predict(donor).p_survive_90d
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from app.ml.churn import ChurnPrediction as _ChurnPrediction
from app.ml.churn import ChurnPredictor as _ChurnPredictor
from app.ml.churn import load_predictor as _load_churn
from app.ml.utils import haversine_km  # noqa: F401 — re-exported for back-compat


# Public names old callers import
__all__ = [
    "StabilityPredictor",
    "StabilityPrediction",
    "DonorFeatures",
    "Factor",
    "extract_features",
    "get_predictor",
    "haversine_km",
    "MODEL_VERSION",
    "FEATURE_NAMES",
]


MODEL_VERSION = "churn_v2_real_data"

# Old code expected a `FEATURE_NAMES` constant — surface the new model's names
# so anything reading this list keeps working.
try:
    from app.ml.features_v2 import FEATURE_NAMES  # type: ignore[import-not-found]
except Exception:
    FEATURE_NAMES: list[str] = []


@dataclass
class Factor:
    """SHAP-style factor (carries through the new model's top features)."""

    feature: str
    label: str
    direction: str  # "increases_churn" | "decreases_churn"
    impact: float
    value: float = 0.0


@dataclass
class DonorFeatures:
    """Compat wrapper.

    Old `extract_features(donor, bridge, today)` returned a feature vector
    object that the predictor consumed. The new predictor takes a Donor
    directly. So this dataclass just carries the Donor through.
    """

    donor: object


@dataclass
class StabilityPrediction:
    """Old per-donor prediction shape — now backed by ChurnPrediction.

    Properties (computed on demand):
        churn_90d  ≈ 1 − p_active
        churn_60d  ≈ churn_90d × 0.85   (decay approximation)
        churn_30d  ≈ churn_90d × 0.60
    """

    p_active: float
    p_not_donated_1y: float
    p_limited_despite_calls: float
    predicted_class: str
    predicted_label: str
    recommended_action: str
    top_factors: list[Factor] = field(default_factory=list)

    @property
    def churn_90d(self) -> float:
        return max(0.0, min(1.0, 1.0 - self.p_active))

    @property
    def churn_60d(self) -> float:
        return max(0.0, min(1.0, self.churn_90d * 0.85))

    @property
    def churn_30d(self) -> float:
        return max(0.0, min(1.0, self.churn_90d * 0.60))


def _to_factor(raw: dict) -> Factor:
    name = str(raw.get("feature", ""))
    importance = float(raw.get("global_importance", 0.0))
    value = float(raw.get("value", 0.0))
    # Heuristic: tree models don't carry sign per-prediction, so we infer from feature
    # semantics — features named "days_since_*" tend to increase churn when high.
    direction = "increases_churn"
    if name in {"donations_till_date", "is_regular", "donated_earlier", "has_blood_group"}:
        # Higher = more engaged = less churn
        direction = "decreases_churn"
    return Factor(
        feature=name,
        label=name.replace("_", " ").title(),
        direction=direction,
        impact=importance,
        value=value,
    )


def _adapt(p: _ChurnPrediction) -> StabilityPrediction:
    return StabilityPrediction(
        p_active=p.p_active,
        p_not_donated_1y=p.p_not_donated_1y,
        p_limited_despite_calls=p.p_limited_despite_calls,
        predicted_class=p.predicted_class,
        predicted_label=p.predicted_label,
        recommended_action=p.recommended_action,
        top_factors=[_to_factor(f) for f in p.top_factors],
    )


class StabilityPredictor:
    """Adapter wrapping the new real-data ChurnPredictor.

    Old API:
        predictor.predict_batch([DonorFeatures(donor=d), ...]) -> list[StabilityPrediction]
        predictor.predict(DonorFeatures(donor=d)) -> StabilityPrediction
    """

    def __init__(self, churn: _ChurnPredictor):
        self._churn = churn

    # Expose churn predictor's metadata so analytics + bake-off readouts work
    @property
    def winner(self) -> str:
        return getattr(self._churn, "winner", "unknown")

    @property
    def metrics(self) -> dict:
        return getattr(self._churn, "metrics", {}) or {}

    @property
    def feature_names(self) -> list[str]:
        return getattr(self._churn, "feature_names", []) or []

    def predict(self, features: DonorFeatures | object) -> StabilityPrediction:
        return self.predict_batch([features])[0]

    def predict_batch(self, features_list: Iterable) -> list[StabilityPrediction]:
        donors = []
        for f in features_list:
            if isinstance(f, DonorFeatures):
                donors.append(f.donor)
            else:
                donors.append(f)  # raw donor passthrough
        preds = self._churn.predict_batch(donors)
        return [_adapt(p) for p in preds]


def extract_features(donor, bridge=None, today: Optional[date] = None) -> DonorFeatures:
    """Compat: old signature took donor + bridge + today.

    The new ChurnPredictor extracts features from the Donor internally, so we
    just wrap the donor and the new predictor pulls what it needs.
    """
    return DonorFeatures(donor=donor)


def get_predictor() -> StabilityPredictor | None:
    """Load the real-data churn predictor and wrap it in the compat adapter.

    Returns None if no model artifact is on disk yet (run
    `python -m app.ml.churn.bakeoff` to train).
    """
    churn = _load_churn()
    if churn is None:
        return None
    return StabilityPredictor(churn=churn)
