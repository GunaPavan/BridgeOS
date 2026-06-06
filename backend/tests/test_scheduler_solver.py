"""Unit tests for the OR-Tools rotation solver (pure function — no DB)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.ml.scheduler.solver import (
    DEFERRAL_DAYS,
    DonorInput,
    SolverStatus,
    solve_rotation,
)


def _donor(name: str, *, last: date | None = None, response: float = 0.9, distance: float = 5.0) -> DonorInput:
    return DonorInput(
        donor_id=uuid.uuid4(),
        name=name,
        blood_group="O+",
        last_donation_date=last,
        response_rate=response,
        distance_km=distance,
    )


def test_solver_produces_one_assignment_per_transfusion_date() -> None:
    today = date(2026, 6, 1)
    donors = [_donor(f"D{i}") for i in range(8)]
    res = solve_rotation(
        donors=donors,
        last_transfusion_date=today - timedelta(days=12),
        cadence_days=18,
        today=today,
        horizon_days=180,
    )
    assert res.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
    # 180/18 = 10 slots
    assert len(res.slots) == 10
    seqs = [s.sequence for s in res.slots]
    assert seqs == list(range(1, 11))


def test_solver_respects_90_day_deferral_between_assignments() -> None:
    today = date(2026, 6, 1)
    donors = [_donor(f"D{i}") for i in range(8)]
    res = solve_rotation(
        donors=donors,
        last_transfusion_date=today - timedelta(days=12),
        cadence_days=18,
        today=today,
        horizon_days=365,
    )
    by_donor: dict[uuid.UUID, list[date]] = {}
    for slot in res.slots:
        by_donor.setdefault(slot.donor_id, []).append(slot.transfusion_date)
    for donor_id, dates in by_donor.items():
        dates_sorted = sorted(dates)
        for a, b in zip(dates_sorted, dates_sorted[1:]):
            gap = (b - a).days
            assert gap >= DEFERRAL_DAYS, (
                f"Donor {donor_id} reassigned with only {gap}d gap"
            )


def test_solver_respects_donor_eligibility_window_from_prior_donation() -> None:
    today = date(2026, 6, 1)
    donors = [_donor(f"D{i}") for i in range(7)]
    # One donor donated 10 days ago — must not be assigned to any slot in next 80 days
    donors.append(_donor("Recent", last=today - timedelta(days=10)))
    res = solve_rotation(
        donors=donors,
        last_transfusion_date=today - timedelta(days=12),
        cadence_days=18,
        today=today,
        horizon_days=200,
    )
    assert res.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
    recent_id = donors[-1].donor_id
    for slot in res.slots:
        if slot.donor_id == recent_id:
            days_from_today = (slot.transfusion_date - today).days
            # First eligibility is at today + (90 - 10) = today + 80 days
            assert days_from_today >= 80, (
                f"Recent donor scheduled too early: {days_from_today}d from today"
            )


def test_solver_prefers_closer_higher_response_donors() -> None:
    """When everyone is otherwise interchangeable, the cheaper donor should be picked."""
    today = date(2026, 6, 1)
    cheap = _donor("Cheap", response=0.95, distance=1.0)
    expensive = _donor("Expensive", response=0.55, distance=40.0)
    res = solve_rotation(
        donors=[cheap, expensive],
        last_transfusion_date=today - timedelta(days=18),
        cadence_days=18,
        today=today,
        horizon_days=90,  # 5 slots; can't all be one donor due to 90-day deferral
    )
    assignments = {s.donor_id: 0 for s in [cheap, expensive]}
    for s in res.slots:
        assignments[s.donor_id] = assignments.get(s.donor_id, 0) + 1
    assert assignments[cheap.donor_id] >= assignments[expensive.donor_id]


def test_solver_reports_donor_load_summing_to_slot_count() -> None:
    today = date(2026, 6, 1)
    donors = [_donor(f"D{i}") for i in range(8)]
    res = solve_rotation(
        donors=donors,
        last_transfusion_date=today - timedelta(days=12),
        cadence_days=18,
        today=today,
        horizon_days=365,
    )
    total_load = sum(d.assignment_count for d in res.donor_load)
    assert total_load == len(res.slots)


def test_solver_returns_empty_when_no_transfusions_in_horizon() -> None:
    today = date(2026, 6, 1)
    donors = [_donor("solo")]
    # Cadence is 18d but last transfusion was just today — next is 18 days out;
    # if horizon is only 10 days, no slot lands inside.
    res = solve_rotation(
        donors=donors,
        last_transfusion_date=today,
        cadence_days=18,
        today=today,
        horizon_days=10,
    )
    assert res.status == SolverStatus.EMPTY
    assert res.slots == []


def test_solver_infeasible_when_no_donor_can_cover_first_slot() -> None:
    """Single donor who's recently donated → cannot cover an imminent slot."""
    today = date(2026, 6, 1)
    donors = [_donor("Recent", last=today - timedelta(days=5))]  # eligible only after day 85
    res = solve_rotation(
        donors=donors,
        last_transfusion_date=today - timedelta(days=17),  # next slot tomorrow
        cadence_days=18,
        today=today,
        horizon_days=30,
    )
    assert res.status == SolverStatus.INFEASIBLE


def test_solver_solve_time_recorded() -> None:
    today = date(2026, 6, 1)
    donors = [_donor(f"D{i}") for i in range(8)]
    res = solve_rotation(
        donors=donors,
        last_transfusion_date=today - timedelta(days=12),
        cadence_days=18,
        today=today,
        horizon_days=365,
    )
    assert res.solve_time_ms >= 0
    assert res.solve_time_ms < 10_000  # safety: must solve in well under 10s
