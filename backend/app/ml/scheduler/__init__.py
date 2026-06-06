"""Rotation Scheduler — Phase 5.

Constraint-satisfaction solver (Google OR-Tools CP-SAT) that produces a
12-month transfusion rotation for one Blood Bridge, respecting the 90-day
donor-deferral × patient-cadence × cohort-size problem.
"""

from app.ml.scheduler.solver import (
    DonorInput,
    ScheduleResult,
    ScheduleSlot,
    SolverStatus,
    solve_rotation,
)
from app.ml.scheduler.service import compute_schedule_for_bridge

__all__ = [
    "DonorInput",
    "ScheduleSlot",
    "ScheduleResult",
    "SolverStatus",
    "solve_rotation",
    "compute_schedule_for_bridge",
]
