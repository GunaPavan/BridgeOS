"""Multi-class Donor Churn Classifier — trained on Blood Warriors data.

Three-class XGBoost model that distinguishes:
    0 — ACTIVE              (continuing donor)
    1 — INACTIVE_NOT_DONATED_1Y     (forgot but still on radar — send reminder)
    2 — INACTIVE_LIMITED_DESPITE_CALLS  (burnout — stop calling)

Public surface:
    train_churn_model(db, out_dir) -> ChurnTrainingReport
    load_predictor(model_dir) -> ChurnPredictor
    extract_donor_features(donor) -> ChurnFeatures
"""

from app.ml.churn.features import ChurnFeatures, extract_donor_features
from app.ml.churn.predictor import ChurnPredictor, ChurnPrediction, load_predictor

__all__ = [
    "ChurnFeatures",
    "extract_donor_features",
    "ChurnPredictor",
    "ChurnPrediction",
    "load_predictor",
]
