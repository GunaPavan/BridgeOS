"""Bridges API: list and detail endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import (
    BloodGroup,
    Bridge,
    BridgeMembership,
    BridgeStatus,
    MembershipStatus,
    Patient,
)
from app.models.enums import BridgeHealth
from app.schemas import (
    BridgeDetail,
    BridgeListItem,
    BridgesPage,
    DonorSummary,
    MembershipDetail,
    PatientDetail,
)

router = APIRouter(prefix="/bridges", tags=["bridges"])


def _bridge_to_list_item(bridge: Bridge) -> BridgeListItem:
    """Map a Bridge ORM row into the list-view DTO."""
    patient = bridge.patient
    return BridgeListItem(
        id=bridge.id,
        patient_id=patient.id,
        patient_name=patient.name,
        patient_age=patient.age,
        blood_group=patient.blood_group,
        city=patient.city,
        state=patient.state,
        hospital=patient.hospital,
        status=bridge.status,
        active_donor_count=bridge.active_donor_count,
        total_donor_count=bridge.total_donor_count,
        health=bridge.health,
        last_transfusion_date=patient.last_transfusion_date,
        next_transfusion_date=patient.next_transfusion_date,
        days_until_transfusion=patient.days_until_transfusion,
        created_at=bridge.created_at,
    )


def _bridge_to_detail(bridge: Bridge) -> BridgeDetail:
    """Map a Bridge ORM row into the full detail DTO."""
    base = _bridge_to_list_item(bridge).model_dump()
    members = [
        MembershipDetail(
            id=m.id,
            role=m.role,
            status=m.status,
            joined_at=m.joined_at,
            notes=m.notes,
            donor=DonorSummary.model_validate(m.donor),
        )
        for m in bridge.memberships
    ]
    return BridgeDetail(
        **base,
        name=bridge.name,
        patient=PatientDetail.model_validate(bridge.patient),
        members=members,
    )


@router.get("", response_model=BridgesPage, summary="List bridges")
def list_bridges(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    health: BridgeHealth | None = Query(
        None,
        description="Filter by computed cohort health (stable | at_risk | critical)",
    ),
    bridge_status: BridgeStatus | None = Query(
        None,
        alias="status",
        description="Filter by bridge lifecycle status (active | paused | closed)",
    ),
    city: str | None = Query(None, description="Filter by patient city (case-insensitive exact)"),
    blood_group: BloodGroup | None = Query(
        None, description="Filter by patient blood group (matches bridge demand)"
    ),
    search: str | None = Query(
        None, description="Substring match on patient name (case-insensitive)"
    ),
    db: Session = Depends(get_db),
) -> BridgesPage:
    """Return paginated bridges with patient summary and stub health.

    Filters compose with AND. `health` is post-applied in Python because it's
    a computed property of `Bridge` (depends on active-membership count) —
    fine at this scale (50 bridges); revisit if the dataset grows past ~5k.
    """
    # SQL-side filters via JOIN to Patient
    conditions = []
    if bridge_status is not None:
        conditions.append(Bridge.status == bridge_status.value)
    if city:
        conditions.append(func.lower(Patient.city) == city.lower())
    if blood_group is not None:
        conditions.append(Patient.blood_group == blood_group.value)
    if search:
        conditions.append(Patient.name.ilike(f"%{search}%"))

    stmt = (
        select(Bridge)
        .join(Patient, Bridge.patient_id == Patient.id)
        .options(joinedload(Bridge.patient), joinedload(Bridge.memberships))
        .order_by(Bridge.created_at.desc())
    )
    if conditions:
        stmt = stmt.where(*conditions)

    bridges = db.execute(stmt).unique().scalars().all()

    # Post-filter by health (computed property, can't push down to SQL cheaply)
    if health is not None:
        bridges = [b for b in bridges if b.health == health]

    total = len(bridges)
    page = bridges[skip : skip + limit]
    items = [_bridge_to_list_item(b) for b in page]
    return BridgesPage(items=items, total=total, skip=skip, limit=limit)


@router.get("/{bridge_id}", response_model=BridgeDetail, summary="Get bridge detail")
def get_bridge(bridge_id: uuid.UUID, db: Session = Depends(get_db)) -> BridgeDetail:
    """Full bridge detail with patient profile and donor cohort."""
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
    return _bridge_to_detail(bridge)
