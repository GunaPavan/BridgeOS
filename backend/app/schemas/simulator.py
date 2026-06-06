"""Simulator schemas."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.recommendation import CandidateOut, WeakDonorOut


class CohortMemberStateOut(BaseModel):
    donor_id: uuid.UUID
    donor_name: str
    blood_group: str
    churn_30d: float
    churn_60d: float
    churn_90d: float


class ScenarioStateOut(BaseModel):
    active_donor_count: int
    cohort: list[CohortMemberStateOut]
    avg_churn_90d: float = Field(ge=0.0, le=1.0)
    max_churn_90d: float = Field(ge=0.0, le=1.0)
    at_risk_count: int
    schedule_status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "EMPTY"]
    schedule_slots_count: int
    schedule_objective: float
    schedule_solve_time_ms: int
    weak_donors: list[WeakDonorOut]
    top_candidates: list[CandidateOut]


class ScenarioDeltaOut(BaseModel):
    cohort_size_change: int
    avg_churn_change: float
    at_risk_change: int
    schedule_slots_change: int
    schedule_objective_change: float


class ScenarioRequest(BaseModel):
    ejected_donor_ids: list[uuid.UUID] = Field(default_factory=list)


class ScenarioOutcomeOut(BaseModel):
    bridge_id: uuid.UUID
    bridge_name: str
    today: date
    requested: ScenarioRequest
    baseline: ScenarioStateOut
    scenario: ScenarioStateOut
    delta: ScenarioDeltaOut
