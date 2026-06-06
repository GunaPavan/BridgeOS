"""Schedule schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

SolverStatusLiteral = Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "EMPTY"]


class ScheduleSlotOut(BaseModel):
    sequence: int
    transfusion_date: date
    donor_id: uuid.UUID
    donor_name: str
    donor_blood_group: str


class DonorLoadOut(BaseModel):
    donor_id: uuid.UUID
    donor_name: str
    assignment_count: int


class BridgeScheduleResponse(BaseModel):
    bridge_id: uuid.UUID
    bridge_name: str
    horizon_days: int
    transfusion_cadence_days: int
    solved_at: datetime
    solve_time_ms: int
    solver_status: SolverStatusLiteral
    objective_value: float
    message: str = Field(default="")
    slots: list[ScheduleSlotOut]
    donor_load: list[DonorLoadOut]
