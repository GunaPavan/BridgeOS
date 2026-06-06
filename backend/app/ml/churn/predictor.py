"""ChurnPredictor — model-agnostic loader for whichever algorithm the
bake-off picked as the winner.

Supports any sklearn-API estimator with `predict_proba`, including XGBoost,
LightGBM, CatBoost, RandomForest, etc. Uses the v2 feature extractor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np

from app.ml.features_v2 import FEATURE_NAMES, GeographicClusterer, extract_features
from app.models import Donor


CLASS_NAMES: list[str] = [
    "active",
    "inactive_not_donated_1y",
    "inactive_limited_despite_calls",
]

CLASS_LABELS: list[str] = [
    "Active",
    "Not donated in 1+ year",
    "Limited engagement despite calls",
]

CLASS_INTERVENTIONS: list[str] = [
    "Continue normal cadence",
    "Send a friendly reminder — donor is likely to convert",
    "Stop calling — try a different channel or accept loss",
]


@dataclass
class ChurnPrediction:
    p_active: float
    p_not_donated_1y: float
    p_limited_despite_calls: float
    predicted_class: str
    predicted_label: str
    recommended_action: str
    top_factors: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "p_active": round(self.p_active, 4),
            "p_not_donated_1y": round(self.p_not_donated_1y, 4),
            "p_limited_despite_calls": round(self.p_limited_despite_calls, 4),
            "predicted_class": self.predicted_class,
            "predicted_label": self.predicted_label,
            "recommended_action": self.recommended_action,
            "top_factors": self.top_factors,
        }


class ChurnPredictor:
    """Wraps the trained classifier from the bake-off."""

    def __init__(
        self,
        model,
        feature_names: list[str],
        metrics: dict | None = None,
        winner: str | None = None,
        geo_clusterer: GeographicClusterer | None = None,
    ):
        self.model = model
        self.feature_names = feature_names
        self.metrics = metrics or {}
        self.winner = winner or "unknown"
        self.geo_clusterer = geo_clusterer

    @classmethod
    def from_dir(cls, model_dir: Path | str) -> "ChurnPredictor":
        d = Path(model_dir)
        model = joblib.load(d / "churn_model.joblib")
        meta = joblib.load(d / "churn_meta.joblib")
        return cls(
            model=model,
            feature_names=meta["feature_names"],
            metrics=meta.get("metrics", {}),
            winner=meta.get("winner", "unknown"),
            geo_clusterer=meta.get("geo_clusterer"),
        )

    def _features_for(self, donor: Donor) -> np.ndarray:
        """Build a single feature vector for a donor, using the trained geo clusterer."""
        geo_id = None
        if self.geo_clusterer is not None:
            lat_lng = np.array([[donor.lat or 0.0, donor.lng or 0.0]], dtype=np.float32)
            geo_id = int(self.geo_clusterer.predict(lat_lng)[0])
        try:
            on_bridge = bool(donor.memberships)
        except Exception:
            on_bridge = False
        feats = extract_features(donor, geo_cluster_id=geo_id, on_bridge=on_bridge)
        return np.array([feats.as_vector()], dtype=np.float32)

    def predict(self, donor: Donor) -> ChurnPrediction:
        return self.predict_batch([donor])[0]

    def predict_batch(self, donors: Iterable[Donor]) -> list[ChurnPrediction]:
        donors_list = list(donors)
        if not donors_list:
            return []
        X = np.vstack([self._features_for(d) for d in donors_list])
        probs = self.model.predict_proba(X)
        out: list[ChurnPrediction] = []
        for i in range(probs.shape[0]):
            row = probs[i]
            cls_idx = int(np.argmax(row))
            out.append(
                ChurnPrediction(
                    p_active=float(row[0]),
                    p_not_donated_1y=float(row[1]),
                    p_limited_despite_calls=float(row[2]),
                    predicted_class=CLASS_NAMES[cls_idx],
                    predicted_label=CLASS_LABELS[cls_idx],
                    recommended_action=CLASS_INTERVENTIONS[cls_idx],
                    top_factors=self._top_factors(X[i]),
                )
            )
        return out

    def _top_factors(self, x_row: np.ndarray) -> list[dict]:
        """Best-effort feature importance (global) attached to each prediction."""
        try:
            importances = getattr(self.model, "feature_importances_", None)
            if importances is None and hasattr(self.model, "named_steps"):
                # Pipeline: try to get importances from the last step
                last = list(self.model.named_steps.values())[-1]
                importances = getattr(last, "feature_importances_", None)
            if importances is None:
                return []
        except Exception:
            return []

        ranked = sorted(enumerate(importances), key=lambda iv: -iv[1])[:3]
        return [
            {
                "feature": self.feature_names[i],
                "global_importance": round(float(imp), 4),
                "value": round(float(x_row[i]), 4),
            }
            for i, imp in ranked
        ]


_global_predictor: ChurnPredictor | None = None


def load_predictor(model_dir: Path | str | None = None) -> ChurnPredictor | None:
    global _global_predictor
    if _global_predictor is not None:
        return _global_predictor
    if model_dir is None:
        model_dir = Path(__file__).parent.parent.parent.parent / "models" / "churn"
    p = Path(model_dir)
    if not (p / "churn_model.joblib").exists():
        return None
    _global_predictor = ChurnPredictor.from_dir(p)
    return _global_predictor


# Backwards-compat helpers — kept for any callers that still pass features rather than donors
def extract_donor_features(donor: Donor, today: date | None = None):
    """Deprecated — kept so existing code doesn't break. Use predictor.predict(donor) instead."""
    return donor
