"""Bridge schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    BloodGroup,
    BridgeHealth,
    BridgeStatus,
    MembershipRole,
    MembershipStatus,
)
from app.schemas.donor import DonorSummary
from app.schemas.patient import PatientDetail


class MembershipDetail(BaseModel):
    """Donor membership in a bridge."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MembershipRole
    status: MembershipStatus
    joined_at: date
    notes: Optional[str]
    donor: DonorSummary


class BridgeListItem(BaseModel):
    """Compact bridge representation for the list view.

    Computed fields (active_donor_count, health, next_transfusion_date,
    days_until_transfusion) are flattened from the ORM properties.
    """

    id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    patient_age: int
    blood_group: BloodGroup
    city: str
    state: str
    hospital: str
    status: BridgeStatus

    active_donor_count: int
    total_donor_count: int
    health: BridgeHealth

    last_transfusion_date: Optional[date]
    next_transfusion_date: Optional[date]
    days_until_transfusion: Optional[int]

    created_at: datetime


class BridgeDetail(BridgeListItem):
    """Full bridge detail including patient profile and donor cohort."""

    name: str
    patient: PatientDetail
    members: list[MembershipDetail]


class BridgesPage(BaseModel):
    """Paginated bridge list response."""

    items: list[BridgeListItem]
    total: int
    skip: int
    limit: int
