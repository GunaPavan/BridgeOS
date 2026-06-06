"""G3 — Auto re-solve schedule on cohort change.

Whenever a membership flips ACTIVE/EXITED (e.g. donor YES → join, donor NO →
no change but worth logging "no_change"), call into this module. It runs the
OR-Tools solver and persists a `ScheduleResolveLog` row capturing the
before/after solver state so the bridge detail page can show coordinators
what changed.

For the hackathon scale (50 bridges, ~8 donors each), each solve is ~50 ms
so running synchronously inside the webhook is fine. For production, this
should move to a background queue.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.ml.scheduler import compute_schedule_for_bridge
from app.ml.scheduler.solver import ScheduleResult
from app.models import Bridge, ScheduleResolveLog


@dataclass
class ResolveOutcome:
    log: ScheduleResolveLog
    before: Optional[ScheduleResult]
    after: ScheduleResult


def _solve(bridge: Bridge, *, horizon_days: int = 365) -> ScheduleResult:
    return compute_schedule_for_bridge(
        bridge=bridge,
        today=date.today(),
        horizon_days=horizon_days,
        time_limit_seconds=5.0,
    )


def auto_resolve_schedule(
    db: Session,
    *,
    bridge: Bridge,
    triggered_by: str,
    before: Optional[ScheduleResult] = None,
    notes: Optional[str] = None,
    commit: bool = False,
    horizon_days: int = 365,
) -> ResolveOutcome:
    """Run the solver and persist a log row.

    Pass `before` when you want before/after deltas (recommended — capture it
    BEFORE you mutate the cohort, then call this AFTER). When omitted, the
    log row records `before_status=None` (caller may not have a baseline).

    Returns the persisted log + before/after snapshots so the caller can echo
    the change in a UI toast / WhatsApp ack.
    """
    after = _solve(bridge, horizon_days=horizon_days)

    log = ScheduleResolveLog(
        bridge_id=bridge.id,
        before_status=before.status.value if before else None,
        after_status=after.status.value,
        before_objective=float(before.objective_value) if before else None,
        after_objective=float(after.objective_value),
        before_slot_count=len(before.slots) if before else None,
        after_slot_count=len(after.slots),
        triggered_by=triggered_by,
        solve_time_ms=int(after.solve_time_ms),
        notes=notes,
    )
    db.add(log)
    if commit:
        db.commit()
        db.refresh(log)

    return ResolveOutcome(log=log, before=before, after=after)


def capture_baseline(bridge: Bridge, *, horizon_days: int = 365) -> ScheduleResult:
    """Solve once to grab the 'before' snapshot — call BEFORE mutating the cohort."""
    return _solve(bridge, horizon_days=horizon_days)


def list_recent_logs(
    db: Session, bridge_id: uuid.UUID, *, limit: int = 5
) -> list[ScheduleResolveLog]:
    """Most-recent-first list of resolve events for the bridge detail page."""
    return list(
        db.execute(
            select(ScheduleResolveLog)
            .where(ScheduleResolveLog.bridge_id == bridge_id)
            .order_by(desc(ScheduleResolveLog.created_at))
            .limit(max(1, min(limit, 50)))
        ).scalars()
    )
