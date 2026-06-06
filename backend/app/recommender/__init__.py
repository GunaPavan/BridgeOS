"""Recommender — Phase 6.

Combines the Cohort Stability Predictor (Phase 4) with the Rotation Scheduler
(Phase 5) to surface at-risk donors per bridge and propose replacement
candidates ranked by distance + response + predicted churn + phenotype match.
"""

from app.recommender.engine import (
    AT_RISK_CHURN_THRESHOLD,
    BridgeRecommendation,
    Candidate,
    CandidateRationale,
    WeakDonor,
    compute_recommendations_for_bridge,
    list_bridges_with_recommendations,
)

__all__ = [
    "AT_RISK_CHURN_THRESHOLD",
    "BridgeRecommendation",
    "WeakDonor",
    "Candidate",
    "CandidateRationale",
    "compute_recommendations_for_bridge",
    "list_bridges_with_recommendations",
]
