"""Time-to-Event Survival Model — Cox Proportional Hazards on Blood Warriors data.

Predicts time-to-disengagement for active donors:
    - Time origin: last_donation_date (or registration_date if never donated)
    - Event:       donor becomes Inactive
    - Censoring:   donor is still Active in the snapshot

Produces hazard ratios per feature (interpretable) and per-donor risk score
that powers the scheduler's outreach timing decisions.

Public surface:
    train_survival_model(out_dir) -> SurvivalTrainingReport
    load_predictor(model_dir) -> SurvivalPredictor
"""

from app.ml.survival.features import SurvivalFeatures, extract_survival_features
from app.ml.survival.predictor import SurvivalPredictor, SurvivalPrediction, load_predictor

__all__ = [
    "SurvivalFeatures",
    "extract_survival_features",
    "SurvivalPredictor",
    "SurvivalPrediction",
    "load_predictor",
]
