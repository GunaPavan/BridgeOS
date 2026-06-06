"""Schedule API: OR-Tools rotation solver exposed over HTTP."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.ml.scheduler import compute_schedule_for_bridge
from app.models import Bridge, BridgeMembership
from app.schemas import BridgeScheduleResponse, DonorLoadOut, ScheduleSlotOut

router = APIRouter(prefix="/bridges", tags=["schedule"])


def _load_bridge(db: Session, bridge_id: uuid.UUID) -> Bridge:
    stmt = (
        select(Bridge)
        .options(
            joinedload(Bridge.patient),
            joinedload(Bridge.memberships).joinedload(BridgeMembership.donor),
        )
        .where(Bridge.id == bridge_id)
    )
    bridge = db.execute(stmt).unique().scalar_one_or_none()
    if bridge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bridge {bridge_id} not found",
        )
    return bridge


@router.get(
    "/{bridge_id}/schedule",
    response_model=BridgeScheduleResponse,
    summary="Solve the 12-month rotation (OR-Tools CP-SAT)",
)
def get_bridge_schedule(
    bridge_id: uuid.UUID,
    horizon_days: int = Query(365, ge=30, le=730),
    time_limit_seconds: float = Query(5.0, ge=0.5, le=30.0),
    db: Session = Depends(get_db),
) -> BridgeScheduleResponse:
    """Return the rotation solution for the given bridge."""
    bridge = _load_bridge(db, bridge_id)
    result = compute_schedule_for_bridge(
        bridge=bridge,
        today=date.today(),
        horizon_days=horizon_days,
        time_limit_seconds=time_limit_seconds,
    )

    if result.status.value == "INFEASIBLE":
        # 422 — request is well-formed, but the solver couldn't find a feasible
        # rotation given the constraints. Surface the message so the UI can
        # explain (typically: too few donors for the horizon).
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.message,
        )

    return BridgeScheduleResponse(
        bridge_id=bridge.id,
        bridge_name=bridge.name,
        horizon_days=result.horizon_days,
        transfusion_cadence_days=result.transfusion_cadence_days,
        solved_at=result.solved_at,
        solve_time_ms=result.solve_time_ms,
        solver_status=result.status.value,
        objective_value=result.objective_value,
        message=result.message,
        slots=[ScheduleSlotOut(**asdict(s)) for s in result.slots],
        donor_load=[DonorLoadOut(**asdict(d)) for d in result.donor_load],
    )


@router.post(
    "/{bridge_id}/schedule/resolve",
    response_model=BridgeScheduleResponse,
    summary="Re-solve the rotation (e.g. after a donor change)",
)
def resolve_bridge_schedule(
    bridge_id: uuid.UUID,
    horizon_days: int = Query(365, ge=30, le=730),
    time_limit_seconds: float = Query(5.0, ge=0.5, le=30.0),
    db: Session = Depends(get_db),
) -> BridgeScheduleResponse:
    """Identical to GET in Phase 5 — both run a fresh solve. Phase 6 will
    consume this for the recruit-and-resolve flow.
    """
    return get_bridge_schedule(
        bridge_id=bridge_id,
        horizon_days=horizon_days,
        time_limit_seconds=time_limit_seconds,
        db=db,
    )


@router.get(
    "/{bridge_id}/swap-requests",
    summary="G6: all swap requests for this bridge (proposed/accepted/rejected/expired)",
)
def get_swap_requests(
    bridge_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """Lists swap requests, most-recent first. Runs the lazy 48h expiry sweep
    on read so the UI never shows stale PROPOSED rows."""
    from app.models import Donor
    from app.services.swap_engine import list_swaps_for_bridge

    # 404 if bridge doesn't exist
    _load_bridge(db, bridge_id)

    rows = list_swaps_for_bridge(db, bridge_id, limit=limit)

    # Resolve donor names in one extra fetch
    donor_ids = {r.from_donor_id for r in rows} | {r.to_donor_id for r in rows}
    name_by_id: dict = {}
    if donor_ids:
        for d in db.execute(select(Donor).where(Donor.id.in_(donor_ids))).scalars():
            name_by_id[d.id] = d.name

    return {
        "bridge_id": str(bridge_id),
        "swaps": [
            {
                "id": str(r.id),
                "from_donor_id": str(r.from_donor_id),
                "from_donor_name": name_by_id.get(r.from_donor_id, "?"),
                "to_donor_id": str(r.to_donor_id),
                "to_donor_name": name_by_id.get(r.to_donor_id, "?"),
                "from_slot_date": r.from_slot_date.isoformat(),
                "to_slot_date": r.to_slot_date.isoformat(),
                "status": getattr(r.status, "value", str(r.status)),
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "accepted_at": r.accepted_at.isoformat() if r.accepted_at else None,
                "rejected_at": r.rejected_at.isoformat() if r.rejected_at else None,
            }
            for r in rows
        ],
    }


@router.get(
    "/{bridge_id}/schedule-history",
    summary="G3: most-recent auto-resolve events for this bridge",
)
def get_schedule_history(
    bridge_id: uuid.UUID,
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """One row per cohort-change-triggered re-solve."""
    from app.services.schedule_resolve import list_recent_logs

    # 404 if bridge doesn't exist
    _load_bridge(db, bridge_id)

    rows = list_recent_logs(db, bridge_id, limit=limit)
    return {
        "bridge_id": str(bridge_id),
        "events": [
            {
                "id": str(r.id),
                "before_status": r.before_status,
                "after_status": r.after_status,
                "before_objective": r.before_objective,
                "after_objective": r.after_objective,
                "before_slot_count": r.before_slot_count,
                "after_slot_count": r.after_slot_count,
                "triggered_by": r.triggered_by,
                "solve_time_ms": r.solve_time_ms,
                "notes": r.notes,
                "at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }
