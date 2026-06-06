"""Donors API: list with filters and detail with bridge memberships."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import (
    BloodGroup,
    Bridge,
    BridgeMembership,
    ContactChannel,
    Donor,
    MembershipStatus,
    Patient,
)
from pydantic import BaseModel, field_validator
from app.schemas import (
    DonorBridgeMembership,
    DonorDetail,
    DonorListItem,
    DonorsPage,
)
from app.schemas.recommendation import PendingActionOut

router = APIRouter(prefix="/donors", tags=["donors"])


SORT_FIELDS = {
    "name": Donor.name,
    "last_donation": Donor.last_donation_date,
    "response_rate": Donor.response_rate,
    "total_donations": Donor.total_donations,
    "age": Donor.age,
}


def _short_handle(external_id: str | None) -> str | None:
    """First 6 hex chars of the CSV ``user_id``, uppercased — the small chip
    rendered beside the donor's real name on /donors cards."""
    if not external_id:
        return None
    s = external_id.lstrip("\\x") if external_id.startswith("\\x") else external_id
    return (s[:6].upper() or None) if s else None


def _to_list_item(donor: Donor, bridge_count: int) -> DonorListItem:
    return DonorListItem(
        id=donor.id,
        external_handle=_short_handle(donor.external_id),
        name=donor.name,
        age=donor.age,
        blood_group=donor.blood_group,
        rh_negative=donor.rh_negative,
        kell_negative=donor.kell_negative,
        city=donor.city,
        state=donor.state,
        preferred_language=donor.preferred_language,
        last_donation_date=donor.last_donation_date,
        days_since_donation=donor.days_since_donation,
        total_donations=donor.total_donations,
        response_rate=donor.response_rate,
        avg_response_hours=donor.avg_response_hours,
        is_active=donor.is_active,
        is_eligible_to_donate=donor.is_eligible_to_donate,
        bridge_count=bridge_count,
    )


@router.get("", response_model=DonorsPage, summary="List donors with filters")
def list_donors(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, description="Match name (case-insensitive substring)"),
    blood_group: BloodGroup | None = Query(None, description="Filter by ABO+Rh group"),
    city: str | None = Query(None, description="Filter by city (exact, case-insensitive)"),
    is_active: bool | None = Query(None),
    kell_negative: bool | None = Query(None),
    sort: str = Query("name", description="Sort field: name|last_donation|response_rate|total_donations|age"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> DonorsPage:
    """Return paginated donors with optional filters and sort."""
    conditions = []
    if search:
        conditions.append(Donor.name.ilike(f"%{search}%"))
    if blood_group is not None:
        conditions.append(Donor.blood_group == blood_group.value)
    if city:
        conditions.append(func.lower(Donor.city) == city.lower())
    if is_active is not None:
        conditions.append(Donor.is_active.is_(is_active))
    if kell_negative is not None:
        conditions.append(Donor.kell_negative.is_(kell_negative))

    where_clause = and_(*conditions) if conditions else None

    sort_col = SORT_FIELDS.get(sort)
    if sort_col is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown sort field '{sort}'. Allowed: {', '.join(SORT_FIELDS)}",
        )
    sort_expr = sort_col.desc() if order == "desc" else sort_col.asc()

    count_stmt = select(func.count()).select_from(Donor)
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
    total = db.execute(count_stmt).scalar_one()

    list_stmt = select(Donor)
    if where_clause is not None:
        list_stmt = list_stmt.where(where_clause)
    list_stmt = list_stmt.order_by(sort_expr, Donor.id).offset(skip).limit(limit)

    donors = db.execute(list_stmt).scalars().all()

    # Bridge counts in one query
    donor_ids = [d.id for d in donors]
    bridge_counts: dict[uuid.UUID, int] = {}
    if donor_ids:
        rows = db.execute(
            select(BridgeMembership.donor_id, func.count(BridgeMembership.id))
            .where(
                BridgeMembership.donor_id.in_(donor_ids),
                BridgeMembership.status == MembershipStatus.ACTIVE,
            )
            .group_by(BridgeMembership.donor_id)
        ).all()
        bridge_counts = {row[0]: row[1] for row in rows}

    items = [_to_list_item(d, bridge_counts.get(d.id, 0)) for d in donors]
    return DonorsPage(items=items, total=total, skip=skip, limit=limit)


@router.get("/{donor_id}", response_model=DonorDetail, summary="Get donor detail")
def get_donor(donor_id: uuid.UUID, db: Session = Depends(get_db)) -> DonorDetail:
    """Full donor profile + every bridge they belong to."""
    stmt = (
        select(Donor)
        .options(
            joinedload(Donor.memberships).joinedload(BridgeMembership.bridge).joinedload(Bridge.patient)
        )
        .where(Donor.id == donor_id)
    )
    donor = db.execute(stmt).unique().scalar_one_or_none()
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Donor {donor_id} not found",
        )

    memberships = [
        DonorBridgeMembership(
            membership_id=m.id,
            bridge_id=m.bridge.id,
            bridge_name=m.bridge.name,
            bridge_status=m.bridge.status,
            patient_id=m.bridge.patient.id,
            patient_name=m.bridge.patient.name,
            patient_age=m.bridge.patient.age,
            patient_blood_group=m.bridge.patient.blood_group,
            role=m.role,
            status=m.status,
            joined_at=m.joined_at,
        )
        for m in donor.memberships
    ]
    active_count = sum(1 for m in memberships if m.status == MembershipStatus.ACTIVE)

    base = _to_list_item(donor, active_count)
    return DonorDetail(
        **base.model_dump(),
        phone=donor.phone,
        lat=donor.lat,
        lng=donor.lng,
        extended_phenotype=donor.extended_phenotype,
        registered_at=donor.registered_at,
        memberships=memberships,
    )


@router.get(
    "/{donor_id}/response-history",
    summary="EMA-replay events for the donor's response_rate sparkline (G2)",
)
def get_response_history(
    donor_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365, description="Lookback window in days (1-365)"),
    db: Session = Depends(get_db),
) -> dict:
    """Returns the rolling EMA points the UI sparkline draws from.

    Each event records the prior + new response_rate so the UI can replay
    the curve without recomputing anything. Sorted oldest → newest.
    """
    from app.services.response_feedback import apply_no_reply_decay, response_history

    donor = db.get(Donor, donor_id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Donor {donor_id} not found",
        )

    # Catch up any pending no-reply decay first so the sparkline ends at the
    # current donor.response_rate.
    apply_no_reply_decay(db, donor=donor, commit=False)
    db.flush()

    events = response_history(db, donor_id, days=max(1, min(days, 365)))
    points = [
        {
            "kind": getattr(e.kind, "value", str(e.kind)),
            "prior_response_rate": e.prior_response_rate,
            "new_response_rate": e.new_response_rate,
            "prior_avg_hours": e.prior_avg_hours,
            "new_avg_hours": e.new_avg_hours,
            "hours_to_response": e.hours_to_response,
            "at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]
    return {
        "donor_id": str(donor.id),
        "donor_name": donor.name,
        "current_response_rate": float(donor.response_rate),
        "current_avg_response_hours": float(donor.avg_response_hours),
        "events": points,
        "days": days,
    }


@router.get(
    "/{donor_id}/pending-actions",
    response_model=list[PendingActionOut],
    summary="Pending actions this donor can ACCEPT / DECLINE via WhatsApp",
)
def list_pending_actions(
    donor_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[PendingActionOut]:
    """G1: every PENDING membership this donor has.

    Today the only PendingAction kind is `recruit` (PENDING BridgeMembership
    waiting on YES/NO). Phase G6 will add `swap_request` to the same list.
    """
    # 404 on unknown donor so callers can distinguish "no pending actions"
    # from "this donor doesn't exist" — every other /donors/{id}/* endpoint
    # already does this; pending-actions used to silently return [].
    if db.get(Donor, donor_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Donor {donor_id} not found",
        )
    rows = (
        db.execute(
            select(BridgeMembership)
            .where(
                BridgeMembership.donor_id == donor_id,
                BridgeMembership.status == MembershipStatus.PENDING.value,
            )
            .options(
                joinedload(BridgeMembership.bridge).joinedload(Bridge.patient),
            )
        )
        .scalars()
        .all()
    )
    out: list[PendingActionOut] = []
    for m in rows:
        replaces_name = None
        if m.replaces_donor_id is not None:
            r = db.get(Donor, m.replaces_donor_id)
            replaces_name = r.name if r else None
        out.append(
            PendingActionOut(
                kind="recruit",
                membership_id=m.id,
                bridge_id=m.bridge.id,
                bridge_name=m.bridge.name,
                patient_name=m.bridge.patient.name,
                replaces_donor_name=replaces_name,
                invite_sent_at=m.joined_at,
            )
        )
    return out


# ---------------------------------------------------------------------------
# E6 — channel preference CRUD
# ---------------------------------------------------------------------------


class ChannelUpdateRequest(BaseModel):
    """Payload for setting a donor's preferred outbound channel."""

    preferred_channel: ContactChannel

    @field_validator("preferred_channel", mode="before")
    @classmethod
    def _normalise(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v


class ChannelInfoOut(BaseModel):
    donor_id: uuid.UUID
    name: str
    phone: str
    preferred_channel: ContactChannel


@router.get(
    "/{donor_id}/channel",
    response_model=ChannelInfoOut,
    summary="E6: read a donor's preferred outbound channel",
)
def get_channel(donor_id: uuid.UUID, db: Session = Depends(get_db)) -> ChannelInfoOut:
    d = db.get(Donor, donor_id)
    if d is None:
        raise HTTPException(404, detail=f"Donor {donor_id} not found")
    return ChannelInfoOut(
        donor_id=d.id,
        name=d.name,
        phone=d.phone,
        preferred_channel=ContactChannel(
            getattr(d.preferred_channel, "value", str(d.preferred_channel))
        ),
    )


@router.patch(
    "/{donor_id}/channel",
    response_model=ChannelInfoOut,
    summary="E6: set a donor's preferred outbound channel (sms | whatsapp | email)",
)
def patch_channel(
    donor_id: uuid.UUID,
    payload: ChannelUpdateRequest,
    db: Session = Depends(get_db),
) -> ChannelInfoOut:
    d = db.get(Donor, donor_id)
    if d is None:
        raise HTTPException(404, detail=f"Donor {donor_id} not found")
    if payload.preferred_channel == ContactChannel.EMAIL:
        raise HTTPException(
            400,
            detail=(
                "Email is caregiver-only; donors can be SMS or WHATSAPP. "
                "Use /patients/{id}/caregiver-channel for caregiver email."
            ),
        )
    d.preferred_channel = payload.preferred_channel
    db.commit()
    db.refresh(d)
    return ChannelInfoOut(
        donor_id=d.id,
        name=d.name,
        phone=d.phone,
        preferred_channel=ContactChannel(
            getattr(d.preferred_channel, "value", str(d.preferred_channel))
        ),
    )
