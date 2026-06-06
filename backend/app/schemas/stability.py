"""Stability prediction schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import BridgeHealth


class StabilityFactor(BaseModel):
    """One SHAP-driven factor explaining a donor's churn probability."""

    feature: str = Field(description="Raw feature name (e.g. response_rate)")
    label: str = Field(description="Human-readable phrase for the UI")
    direction: Literal["increases_churn", "decreases_churn"]
    impact: float = Field(description="Absolute SHAP value — bigger means stronger driver")


class DonorStability(BaseModel):
    """Per-donor stability prediction within one bridge."""

    donor_id: uuid.UUID
    donor_name: str
    churn_30d: float = Field(ge=0.0, le=1.0)
    churn_60d: float = Field(ge=0.0, le=1.0)
    churn_90d: float = Field(ge=0.0, le=1.0)
    top_factors: list[StabilityFactor]


class BridgeStabilityAggregate(BaseModel):
    """Bridge-level summary of the cohort's stability."""

    ml_health: BridgeHealth = Field(description="ML-driven health (overrides Phase 1 stub)")
    avg_churn_90d: float = Field(ge=0.0, le=1.0)
    max_churn_90d: float = Field(ge=0.0, le=1.0)
    at_risk_donor_count: int = Field(description="Donors with churn_90d >= 0.5")
    active_donor_count: int


class BridgeStability(BaseModel):
    """Full /bridges/{id}/stability response."""

    bridge_id: uuid.UUID
    bridge_name: str
    computed_at: datetime
    model_version: str
    aggregate: BridgeStabilityAggregate
    members: list[DonorStability]
