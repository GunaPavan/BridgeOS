"""Analytics dashboard schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class HealthCounts(BaseModel):
    stable: int
    at_risk: int
    critical: int

    @property
    def total(self) -> int:
        return self.stable + self.at_risk + self.critical


class BloodGroupBreakdown(BaseModel):
    blood_group: str
    count: int


class CityBreakdown(BaseModel):
    city: str
    state: str
    count: int


class DonorPoolStats(BaseModel):
    total: int
    active: int
    eligible_now: int
    kell_negative: int
    by_blood_group: list[BloodGroupBreakdown]


class CohortStats(BaseModel):
    total_bridges: int
    avg_active_donors: float
    avg_cohort_size: float
    total_active_memberships: int
    stub_health: HealthCounts = Field(
        description="Phase 1 health stub (active donor count)"
    )
    ml_health: HealthCounts = Field(
        description="Phase 4 ML-derived health (XGBoost-aggregated)"
    )


class StabilityModelMetrics(BaseModel):
    trained_at: str
    n_samples: int
    seed: int
    auc_30d: float
    auc_60d: float
    auc_90d: float
    train_auc_30d: float
    train_auc_60d: float
    train_auc_90d: float
    brier_90d: float


class AnalyticsResponse(BaseModel):
    generated_at: datetime
    total_patients: int
    total_donors: int
    donor_pool: DonorPoolStats
    cohort_stats: CohortStats
    patients_by_city: list[CityBreakdown]
    stability_model: Optional[StabilityModelMetrics] = None
    stability_compute_time_ms: int = Field(
        description="Time spent running the stability model across all bridges"
    )
