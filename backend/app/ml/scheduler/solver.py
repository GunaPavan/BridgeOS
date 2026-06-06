"""OR-Tools CP-SAT rotation solver.

Pure-function interface: takes plain Python dataclasses (no SQLAlchemy
coupling), returns a schedule. Lives behind the `service.py` orchestrator
that knows how to load ORM rows.

The model:
  - Decision variables: assignment[t] in [0..n_donors-1] for each transfusion t
  - Hard constraints:
      * Donor's prior real-world donation creates an ineligibility window
        starting today (no assignment to slots inside that window)
      * Two assignments to the same donor must be >= 90 days apart
      * Load cap per donor (derived from horizon_days / 90)
  - Objective (minimise):
      * distance_km × 10  (closer = cheaper)
      * (1 - response_rate) × 1000  (more reliable = cheaper)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Optional
from uuid import UUID

from ortools.sat.python import cp_model

DEFERRAL_DAYS = 90


class SolverStatus(str, Enum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    EMPTY = "EMPTY"  # no transfusion slots in the horizon


@dataclass(frozen=True)
class DonorInput:
    """Plain donor data needed by the solver."""

    donor_id: UUID
    name: str
    blood_group: str
    last_donation_date: Optional[date]
    response_rate: float
    distance_km: float


@dataclass(frozen=True)
class ScheduleSlot:
    sequence: int
    transfusion_date: date
    donor_id: UUID
    donor_name: str
    donor_blood_group: str


@dataclass(frozen=True)
class DonorLoad:
    donor_id: UUID
    donor_name: str
    assignment_count: int


@dataclass(frozen=True)
class ScheduleResult:
    status: SolverStatus
    horizon_days: int
    transfusion_cadence_days: int
    solved_at: datetime
    solve_time_ms: int
    objective_value: float
    slots: list[ScheduleSlot] = field(default_factory=list)
    donor_load: list[DonorLoad] = field(default_factory=list)
    message: str = ""


def _transfusion_dates(
    last_transfusion_date: Optional[date],
    cadence_days: int,
    today: date,
    horizon_days: int,
) -> list[date]:
    """Compute the calendar dates of transfusions in the horizon (inclusive of today)."""
    if cadence_days <= 0:
        return []
    anchor = last_transfusion_date or today
    end = today + timedelta(days=horizon_days)
    dates: list[date] = []
    candidate = anchor + timedelta(days=cadence_days)
    # Walk forward from the next scheduled date after last_transfusion
    while candidate <= end:
        if candidate >= today:
            dates.append(candidate)
        candidate += timedelta(days=cadence_days)
    return dates


def _days_until_eligible(donor: DonorInput, today: date) -> int:
    """How many days from `today` before this donor can give again."""
    if donor.last_donation_date is None:
        return 0
    gap = (today - donor.last_donation_date).days
    return max(0, DEFERRAL_DAYS - gap)


def solve_rotation(
    donors: list[DonorInput],
    last_transfusion_date: Optional[date],
    cadence_days: int,
    today: date,
    horizon_days: int = 365,
    time_limit_seconds: float = 5.0,
) -> ScheduleResult:
    """Solve the rotation. Returns a `ScheduleResult` with status + slots."""
    started = datetime.now(timezone.utc)
    tx_dates = _transfusion_dates(last_transfusion_date, cadence_days, today, horizon_days)
    n_slots = len(tx_dates)
    n_donors = len(donors)

    if n_slots == 0 or n_donors == 0:
        return ScheduleResult(
            status=SolverStatus.EMPTY,
            horizon_days=horizon_days,
            transfusion_cadence_days=cadence_days,
            solved_at=started,
            solve_time_ms=0,
            objective_value=0.0,
            message=(
                "No transfusion slots in horizon" if n_slots == 0 else "No donors available"
            ),
        )

    # Load cap: max(2, ceil(horizon_days / DEFERRAL_DAYS) + 1)
    # With horizon=365, deferral=90 -> ceil(365/90)+1 = 6, so each donor max 6 slots
    physical_max = math.ceil(horizon_days / DEFERRAL_DAYS) + 1
    # Fairness cap: don't let any one donor cover more than (n_slots / n_donors) + 2
    fair_max = math.ceil(n_slots / n_donors) + 2
    max_load = max(2, min(physical_max, fair_max))

    model = cp_model.CpModel()

    assignment = [
        model.NewIntVar(0, n_donors - 1, f"slot_{t}") for t in range(n_slots)
    ]

    # 1) Donor-eligibility windows from prior real-world donations
    for d_idx, donor in enumerate(donors):
        days_wait = _days_until_eligible(donor, today)
        for t_idx, tx_date in enumerate(tx_dates):
            if (tx_date - today).days < days_wait:
                model.Add(assignment[t_idx] != d_idx)

    # 2) 90-day spacing between two assignments to the same donor
    for t1 in range(n_slots):
        for t2 in range(t1 + 1, n_slots):
            if (tx_dates[t2] - tx_dates[t1]).days < DEFERRAL_DAYS:
                model.Add(assignment[t1] != assignment[t2])

    # 3) Load fairness — booleans channelled from assignment
    is_assigned = [
        [model.NewBoolVar(f"is_{d}_at_{t}") for t in range(n_slots)]
        for d in range(n_donors)
    ]
    for d in range(n_donors):
        for t in range(n_slots):
            model.Add(assignment[t] == d).OnlyEnforceIf(is_assigned[d][t])
            model.Add(assignment[t] != d).OnlyEnforceIf(is_assigned[d][t].Not())
        model.Add(sum(is_assigned[d]) <= max_load)

    # Objective: minimise distance + (1 - response_rate) for each slot
    distance_int = [int(round(d.distance_km * 10)) for d in donors]
    response_int = [int(round((1.0 - d.response_rate) * 1000)) for d in donors]
    donor_costs = [distance_int[d] + response_int[d] for d in range(n_donors)]

    slot_costs = []
    max_cost = max(donor_costs) + 1
    for t in range(n_slots):
        c = model.NewIntVar(0, max_cost, f"cost_{t}")
        model.AddElement(assignment[t], donor_costs, c)
        slot_costs.append(c)
    model.Minimize(sum(slot_costs))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 4
    status = solver.Solve(model)

    elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)

    if status == cp_model.OPTIMAL:
        sstatus = SolverStatus.OPTIMAL
    elif status == cp_model.FEASIBLE:
        sstatus = SolverStatus.FEASIBLE
    else:
        return ScheduleResult(
            status=SolverStatus.INFEASIBLE,
            horizon_days=horizon_days,
            transfusion_cadence_days=cadence_days,
            solved_at=started,
            solve_time_ms=elapsed_ms,
            objective_value=0.0,
            message=(
                "No feasible rotation found. Likely too few donors for the "
                "deferral × cadence × horizon constraints."
            ),
        )

    slots: list[ScheduleSlot] = []
    counts: dict[UUID, int] = {d.donor_id: 0 for d in donors}
    for t_idx in range(n_slots):
        d_idx = int(solver.Value(assignment[t_idx]))
        donor = donors[d_idx]
        slots.append(
            ScheduleSlot(
                sequence=t_idx + 1,
                transfusion_date=tx_dates[t_idx],
                donor_id=donor.donor_id,
                donor_name=donor.name,
                donor_blood_group=donor.blood_group,
            )
        )
        counts[donor.donor_id] += 1

    donor_load = [
        DonorLoad(donor_id=d.donor_id, donor_name=d.name, assignment_count=counts[d.donor_id])
        for d in donors
    ]

    return ScheduleResult(
        status=sstatus,
        horizon_days=horizon_days,
        transfusion_cadence_days=cadence_days,
        solved_at=started,
        solve_time_ms=elapsed_ms,
        objective_value=float(solver.ObjectiveValue()),
        slots=slots,
        donor_load=donor_load,
    )
