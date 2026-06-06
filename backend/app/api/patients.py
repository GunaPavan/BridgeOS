"""Patients API: list with filters and detail with bridge + projected transfusions."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import (
    BloodGroup,
    Bridge,
    BridgeHealth,
    BridgeMembership,
    ContactChannel,
    MembershipStatus,
    Patient,
)
from pydantic import BaseModel, EmailStr, field_validator
from app.schemas import (
    PatientBridgeRef,
    PatientListItem,
    PatientProfile,
    PatientsPage,
)

router = APIRouter(prefix="/patients", tags=["patients"])

SORT_FIELDS = {
    "name": Patient.name,
    "age": Patient.age,
    "last_transfusion": Patient.last_transfusion_date,
}


def _projected_transfusions(patient: Patient, n: int = 6) -> list[date]:
    if patient.last_transfusion_date is None:
        return []
    return [
        patient.last_transfusion_date + timedelta(days=(i + 1) * patient.transfusion_cadence_days)
        for i in range(n)
    ]


def _short_handle(external_id: str | None) -> str | None:
    """First 6 hex chars of the CSV ``user_id``, uppercased. Used for the
    small chip beside the patient's real name on UI cards."""
    if not external_id:
        return None
    s = external_id.lstrip("\\x") if external_id.startswith("\\x") else external_id
    return (s[:6] or None).upper() if s else None


def _to_list_item(patient: Patient) -> PatientListItem:
    bridge = patient.bridge
    return PatientListItem(
        id=patient.id,
        external_handle=_short_handle(patient.external_id),
        name=patient.name,
        age=patient.age,
        blood_group=patient.blood_group,
        rh_negative=patient.rh_negative,
        kell_negative=patient.kell_negative,
        city=patient.city,
        state=patient.state,
        hospital=patient.hospital,
        preferred_language=patient.preferred_language,
        transfusion_cadence_days=patient.transfusion_cadence_days,
        last_transfusion_date=patient.last_transfusion_date,
        next_transfusion_date=patient.next_transfusion_date,
        days_until_transfusion=patient.days_until_transfusion,
        active=patient.active,
        has_bridge=bridge is not None,
        bridge_health=bridge.health if bridge else None,
        active_donor_count=bridge.active_donor_count if bridge else 0,
    )


@router.get("", response_model=PatientsPage, summary="List patients with filters")
def list_patients(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, description="Match name (case-insensitive substring)"),
    blood_group: BloodGroup | None = Query(None),
    city: str | None = Query(None),
    active: bool | None = Query(None),
    has_bridge: bool | None = Query(None),
    bridge_health: BridgeHealth | None = Query(None),
    sort: str = Query("name", description="Sort field: name|age|last_transfusion"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> PatientsPage:
    """Return paginated patients with optional filters and sort."""
    conditions = []
    if search:
        conditions.append(Patient.name.ilike(f"%{search}%"))
    if blood_group is not None:
        conditions.append(Patient.blood_group == blood_group.value)
    if city:
        conditions.append(func.lower(Patient.city) == city.lower())
    if active is not None:
        conditions.append(Patient.active.is_(active))
    if has_bridge is not None:
        if has_bridge:
            conditions.append(Patient.bridge.has())
        else:
            conditions.append(~Patient.bridge.has())

    where_clause = and_(*conditions) if conditions else None

    sort_col = SORT_FIELDS.get(sort)
    if sort_col is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown sort field '{sort}'. Allowed: {', '.join(SORT_FIELDS)}",
        )
    sort_expr = sort_col.desc() if order == "desc" else sort_col.asc()

    count_stmt = select(func.count()).select_from(Patient)
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
    total = db.execute(count_stmt).scalar_one()

    list_stmt = (
        select(Patient)
        .options(joinedload(Patient.bridge).joinedload(Bridge.memberships))
    )
    if where_clause is not None:
        list_stmt = list_stmt.where(where_clause)
    list_stmt = list_stmt.order_by(sort_expr, Patient.id).offset(skip).limit(limit)

    patients = db.execute(list_stmt).unique().scalars().all()

    items = [_to_list_item(p) for p in patients]

    # Optional post-filter for bridge_health (can't easily do in SQL because it's derived)
    if bridge_health is not None:
        items = [it for it in items if it.bridge_health == bridge_health]
        # Adjust total to reflect filtered set when bridge_health is provided
        total = len(items)

    return PatientsPage(items=items, total=total, skip=skip, limit=limit)


@router.get("/{patient_id}", response_model=PatientProfile, summary="Get patient profile")
def get_patient(patient_id: uuid.UUID, db: Session = Depends(get_db)) -> PatientProfile:
    """Full patient profile + bridge summary + projected next 6 transfusion dates."""
    stmt = (
        select(Patient)
        .options(joinedload(Patient.bridge).joinedload(Bridge.memberships))
        .where(Patient.id == patient_id)
    )
    patient = db.execute(stmt).unique().scalar_one_or_none()
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient {patient_id} not found",
        )

    bridge_ref = None
    if patient.bridge is not None:
        b = patient.bridge
        bridge_ref = PatientBridgeRef(
            bridge_id=b.id,
            bridge_name=b.name,
            bridge_status=b.status,
            active_donor_count=b.active_donor_count,
            total_donor_count=b.total_donor_count,
            health=b.health,
            created_at=b.created_at,
        )

    base = _to_list_item(patient)
    return PatientProfile(
        **base.model_dump(),
        extended_phenotype=patient.extended_phenotype,
        lat=patient.lat,
        lng=patient.lng,
        registered_at=patient.registered_at,
        bridge=bridge_ref,
        projected_transfusions=_projected_transfusions(patient),
        caregiver_name=patient.caregiver_name,
        caregiver_phone=patient.caregiver_phone,
        caregiver_relation=(
            getattr(patient.caregiver_relation, "value", patient.caregiver_relation)
            if patient.caregiver_relation is not None
            else None
        ),
    )


# ----- G5: caregiver notification -----


class _NotifyCaregiverRequest(__import__("pydantic").BaseModel):
    template_key: str
    language: str | None = None
    added_donor_name: str | None = None


@router.post(
    "/{patient_id}/notify-caregiver",
    summary="G5: send a *_caregiver template to the patient's caregiver",
)
def notify_caregiver(
    patient_id: uuid.UUID,
    payload: _NotifyCaregiverRequest,
    db: Session = Depends(get_db),
) -> dict:
    from app.services.caregiver_notifications import send_caregiver_template
    from app.services.whatsapp_templates import CAREGIVER_TEMPLATE_KEYS

    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient {patient_id} not found",
        )
    if payload.template_key not in CAREGIVER_TEMPLATE_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"template_key '{payload.template_key}' is not a caregiver "
                f"template. Use one of: {sorted(CAREGIVER_TEMPLATE_KEYS)}"
            ),
        )
    if not patient.caregiver_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Patient {patient.name} has no caregiver_phone configured",
        )

    bridge = patient.bridge
    result = send_caregiver_template(
        db,
        patient=patient,
        bridge=bridge,
        template_key=payload.template_key,
        added_donor_name=payload.added_donor_name or "",
        language=payload.language,
        commit=True,
    )
    return {
        "patient_id": str(patient.id),
        "template_key": result.template_key,
        "language_used": result.language_used,
        "fallback_used": result.fallback_used,
        "message_id": str(result.message.id) if result.message else None,
        "message_sid": result.message.twilio_sid if result.message else None,
        "body": result.message.body if result.message else None,
    }


# ---------------------------------------------------------------------------
# E6 — caregiver channel preference + email CRUD
# ---------------------------------------------------------------------------


class CaregiverChannelOut(BaseModel):
    patient_id: uuid.UUID
    patient_name: str
    caregiver_name: str | None
    caregiver_phone: str | None
    caregiver_email: str | None
    caregiver_preferred_channel: ContactChannel


class CaregiverChannelPatch(BaseModel):
    """Partial update — any field omitted is left as-is."""

    caregiver_preferred_channel: ContactChannel | None = None
    caregiver_email: EmailStr | None = None

    @field_validator("caregiver_preferred_channel", mode="before")
    @classmethod
    def _normalise(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v


def _caregiver_out(p: Patient) -> CaregiverChannelOut:
    return CaregiverChannelOut(
        patient_id=p.id,
        patient_name=p.name,
        caregiver_name=p.caregiver_name,
        caregiver_phone=p.caregiver_phone,
        caregiver_email=p.caregiver_email,
        caregiver_preferred_channel=ContactChannel(
            getattr(p.caregiver_preferred_channel, "value", str(p.caregiver_preferred_channel))
        ),
    )


@router.get(
    "/{patient_id}/caregiver-channel",
    response_model=CaregiverChannelOut,
    summary="E6: read the caregiver's preferred channel + email",
)
def get_caregiver_channel(
    patient_id: uuid.UUID, db: Session = Depends(get_db)
) -> CaregiverChannelOut:
    p = db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(404, detail=f"Patient {patient_id} not found")
    return _caregiver_out(p)


@router.patch(
    "/{patient_id}/caregiver-channel",
    response_model=CaregiverChannelOut,
    summary="E6: update caregiver channel + email (partial)",
)
def patch_caregiver_channel(
    patient_id: uuid.UUID,
    payload: CaregiverChannelPatch,
    db: Session = Depends(get_db),
) -> CaregiverChannelOut:
    p = db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(404, detail=f"Patient {patient_id} not found")
    if payload.caregiver_preferred_channel is not None:
        if payload.caregiver_preferred_channel == ContactChannel.EMAIL and not (
            payload.caregiver_email or p.caregiver_email
        ):
            raise HTTPException(
                400,
                detail="Cannot set caregiver channel to EMAIL without an email on file",
            )
        p.caregiver_preferred_channel = payload.caregiver_preferred_channel
    if payload.caregiver_email is not None:
        p.caregiver_email = str(payload.caregiver_email)
    db.commit()
    db.refresh(p)
    return _caregiver_out(p)
