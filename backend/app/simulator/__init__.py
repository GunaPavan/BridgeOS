"""Simulator — Phase 9.

Stateless what-if engine. Given a bridge + a set of "eject" actions, returns
the cohort + stability + schedule + recommendations BOTH before and after the
actions, with deltas. The DB is never written to — the simulator only reads.

This is what powers the drag-drop interactive demo: judge ejects a donor,
watches the system re-rank, re-schedule, and re-recommend in <300 ms.
"""

from app.simulator.engine import (
    Scenario,
    ScenarioOutcome,
    ScenarioState,
    compute_scenario,
)

__all__ = [
    "Scenario",
    "ScenarioOutcome",
    "ScenarioState",
    "compute_scenario",
]
