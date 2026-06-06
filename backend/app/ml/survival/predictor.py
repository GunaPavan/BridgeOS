"""SurvivalPredictor — model-agnostic loader for whichever survival model
the bake-off picked.

Supports: GradientBoostingSurvival / RandomSurvivalForest (scikit-survival),
          Cox PH / Weibull AFT etc. (lifelines),
          XGBoost survival:aft.

Exposes per-donor survival probability at 90 / 180 / 365 days plus a risk
score (relative ordering) suitable for prioritization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np

from app.ml.features_v2 import FEATURE_NAMES, GeographicClusterer, extract_features
from app.models import Donor


@dataclass
class SurvivalPrediction:
    risk_score: float                 # higher = more likely to disengage
    median_survival_days: float | None
    p_survive_90d: float
    p_survive_180d: float
    p_survive_365d: float
    top_factors: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "risk_score": round(self.risk_score, 4),
            "median_survival_days": (
                round(self.median_survival_days, 1)
                if self.median_survival_days is not None
                else None
            ),
            "p_survive_90d": round(self.p_survive_90d, 4),
            "p_survive_180d": round(self.p_survive_180d, 4),
            "p_survive_365d": round(self.p_survive_365d, 4),
            "top_factors": self.top_factors,
        }


class SurvivalPredictor:
    """Wraps the winning survival model (likely GradientBoostingSurvival)."""

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
    def from_dir(cls, model_dir: Path | str) -> "SurvivalPredictor":
        d = Path(model_dir)
        model = joblib.load(d / "survival_model.joblib")
        meta = joblib.load(d / "survival_meta.joblib")
        return cls(
            model=model,
            feature_names=meta["feature_names"],
            metrics=meta.get("metrics", {}),
            winner=meta.get("winner", "unknown"),
            geo_clusterer=meta.get("geo_clusterer"),
        )

    def _features_for(self, donor: Donor) -> np.ndarray:
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

    def predict(self, donor: Donor) -> SurvivalPrediction:
        return self.predict_batch([donor])[0]

    # Lifelines AFT models that need DataFrame input + predict_median.
    _AFT_MODELS = {"Weibull_AFT", "LogNormal_AFT", "LogLogistic_AFT"}

    def predict_batch(self, donors: Iterable[Donor]) -> list[SurvivalPrediction]:
        donors_list = list(donors)
        if not donors_list:
            return []
        X = np.vstack([self._features_for(d) for d in donors_list])

        # Dispatch on the winner type — different libraries have different APIs.
        risk, survival_funcs, median_days = self._invoke_model(X)

        # Top features by importance (global). XGBoost / RSF / GBS expose
        # feature_importances_; lifelines AFT models expose .params_.
        top_ranked = self._global_importance_ranking()

        out: list[SurvivalPrediction] = []
        for i in range(len(donors_list)):
            p90, p180, p365 = self._survival_probs(survival_funcs, i)
            median = self._median(survival_funcs, median_days, i)
            top_factors = [
                {
                    "feature": FEATURE_NAMES[idx],
                    "global_importance": round(float(imp), 4),
                    "value": round(float(X[i][idx]), 4),
                }
                for idx, imp in top_ranked
            ]
            out.append(
                SurvivalPrediction(
                    risk_score=float(risk[i]),
                    median_survival_days=median,
                    p_survive_90d=p90,
                    p_survive_180d=p180,
                    p_survive_365d=p365,
                    top_factors=top_factors,
                )
            )
        return out

    def _invoke_model(self, X: np.ndarray):
        """Run the winning model — different libraries, different APIs.

        Returns ``(risk_per_donor, survival_funcs_or_None, median_days_or_None)``.

        - scikit-survival (GBS / RSF): ``model.predict(X)`` (risk score) +
          ``model.predict_survival_function(X)`` (callable StepFunctions).
        - lifelines (CoxPH / *_AFT): need a DataFrame with named columns;
          they expose ``predict_median(df)`` and (for AFT) survival
          probabilities at queried timepoints.
        - XGBoost AFT: needs ``xgb.DMatrix``.
        """
        winner = (self.winner or "").strip()

        if winner in self._AFT_MODELS:
            import pandas as pd
            df = pd.DataFrame(X, columns=self.feature_names)
            # Median survival time; risk_score = -median (higher = worse)
            median_series = self.model.predict_median(df)
            median_days = np.asarray(median_series).astype(float)
            risk = -median_days.copy()
            # We don't try to evaluate survival_funcs separately; we'll
            # compute p_survive at fixed horizons via predict_survival_function.
            try:
                sf = self.model.predict_survival_function(df, times=[90, 180, 365])
                # sf is a DataFrame: rows=times, cols=donor index
                # Convert to a per-donor dict of {t: prob} so _survival_probs can read it.
                survival_funcs = []
                for col in sf.columns:
                    s90 = float(sf.loc[90, col]) if 90 in sf.index else 1.0
                    s180 = float(sf.loc[180, col]) if 180 in sf.index else 1.0
                    s365 = float(sf.loc[365, col]) if 365 in sf.index else 1.0
                    survival_funcs.append({"90": s90, "180": s180, "365": s365})
            except Exception:
                survival_funcs = None
            return risk, survival_funcs, median_days

        if winner == "CoxPH":
            import pandas as pd
            df = pd.DataFrame(X, columns=self.feature_names)
            risk = np.asarray(self.model.predict_partial_hazard(df)).flatten()
            survival_funcs = None
            try:
                sf = self.model.predict_survival_function(df, times=[90, 180, 365])
                survival_funcs = []
                for col in sf.columns:
                    s90 = float(sf.loc[90, col]) if 90 in sf.index else 1.0
                    s180 = float(sf.loc[180, col]) if 180 in sf.index else 1.0
                    s365 = float(sf.loc[365, col]) if 365 in sf.index else 1.0
                    survival_funcs.append({"90": s90, "180": s180, "365": s365})
            except Exception:
                pass
            return risk, survival_funcs, None

        if winner == "XGBoost_AFT":
            import xgboost as xgb
            risk = np.asarray(self.model.predict(xgb.DMatrix(X))).flatten()
            return risk, None, None

        # scikit-survival path (GradientBoostingSurvival / RandomSurvivalForest)
        risk = np.asarray(self.model.predict(X)).flatten()
        survival_funcs = None
        try:
            survival_funcs = self.model.predict_survival_function(X)
        except Exception:
            pass
        return risk, survival_funcs, None

    def _global_importance_ranking(self) -> list[tuple[int, float]]:
        """Top-3 feature indices ranked by global importance.

        Tree models expose ``feature_importances_``; lifelines AFT models
        expose ``params_`` (coefficients per feature × distribution param).
        We collapse the lifelines params to a single magnitude per feature.
        """
        importances = getattr(self.model, "feature_importances_", None)
        if importances is not None:
            return sorted(enumerate(importances), key=lambda iv: -iv[1])[:3]

        # Lifelines AFT/Cox: try to read coefficients
        try:
            params = self.model.params_
            # params_ for AFT is MultiIndex (param, covariate); aggregate by covariate
            import pandas as pd
            if isinstance(params, pd.Series):
                if isinstance(params.index, pd.MultiIndex):
                    by_feat = params.groupby(level=-1).apply(lambda s: float(np.abs(s).sum()))
                else:
                    by_feat = params.abs()
                # Map covariate name back to FEATURE_NAMES index
                ranked = []
                for feat_name, mag in by_feat.items():
                    if feat_name in self.feature_names:
                        ranked.append((self.feature_names.index(feat_name), float(mag)))
                return sorted(ranked, key=lambda iv: -iv[1])[:3]
        except Exception:
            pass
        return []

    def _survival_probs(self, survival_funcs, i: int) -> tuple[float, float, float]:
        """Read S(t) at t in {90, 180, 365}. Falls back to 1.0 if unavailable.

        ``survival_funcs`` can be:
          - scikit-survival StepFunction list (callable: ``sf(t)`` → float)
          - list of dicts (lifelines path: ``{'90': ..., '180': ..., '365': ...}``)
          - None (model doesn't expose survival function)
        """
        if survival_funcs is None:
            return (1.0, 1.0, 1.0)
        try:
            sf = survival_funcs[i]
            if isinstance(sf, dict):
                return (
                    float(sf.get("90", 1.0)),
                    float(sf.get("180", 1.0)),
                    float(sf.get("365", 1.0)),
                )
            return (
                float(sf(90)),
                float(sf(180)),
                float(sf(365)),
            )
        except Exception:
            return (1.0, 1.0, 1.0)

    def _median(self, survival_funcs, median_days, i: int) -> float | None:
        """Median survival time = the smallest t where S(t) <= 0.5.

        If the model already gave us a direct ``predict_median`` value (AFT
        path), use that. Otherwise walk the survival function curve.
        """
        if median_days is not None:
            try:
                v = float(median_days[i])
                # lifelines returns ``inf`` for donors never expected to event
                if np.isfinite(v) and v > 0:
                    return v
                return None
            except Exception:
                return None
        if survival_funcs is None:
            return None
        try:
            sf = survival_funcs[i]
            if isinstance(sf, dict):
                # Sparse evaluation — can't read median from {90, 180, 365}
                return None
            for t in [30, 60, 90, 120, 180, 270, 365, 540, 730, 1095, 1460]:
                if float(sf(t)) <= 0.5:
                    return float(t)
            return None
        except Exception:
            return None


_global_predictor: SurvivalPredictor | None = None


def load_predictor(model_dir: Path | str | None = None) -> SurvivalPredictor | None:
    global _global_predictor
    if _global_predictor is not None:
        return _global_predictor
    if model_dir is None:
        model_dir = Path(__file__).parent.parent.parent.parent / "models" / "survival"
    p = Path(model_dir)
    if not (p / "survival_model.joblib").exists():
        return None
    _global_predictor = SurvivalPredictor.from_dir(p)
    return _global_predictor


# Backwards-compat helper
def extract_survival_features(donor: Donor):
    """Deprecated — use predictor.predict(donor) directly."""
    return donor
