"""Donor schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    BloodGroup,
    BridgeStatus,
    Language,
    MembershipRole,
    MembershipStatus,
)


class DonorSummary(BaseModel):
    """Compact donor info shown in cohort lists and recommendations."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_handle: Optional[str] = None  # 6-char chip derived from CSV user_id
    name: str
    age: int
    blood_group: BloodGroup
    rh_negative: bool
    kell_negative: bool
    city: str
    state: str
    last_donation_date: Optional[date]
    total_donations: int
    response_rate: float
    is_active: bool


class DonorListItem(BaseModel):
    """Donor row for the /donors list view."""

    id: uuid.UUID
    external_handle: Optional[str] = None  # 6-char chip derived from CSV user_id
    name: str
    age: int
    blood_group: BloodGroup
    rh_negative: bool
    kell_negative: bool
    city: str
    state: str
    preferred_language: Language

    last_donation_date: Optional[date]
    days_since_donation: Optional[int]
    total_donations: int
    response_rate: float
    avg_response_hours: float

    is_active: bool
    is_eligible_to_donate: bool
    bridge_count: int


class DonorBridgeMembership(BaseModel):
    """A bridge this donor is part of (donor-side projection)."""

    membership_id: uuid.UUID
    bridge_id: uuid.UUID
    bridge_name: str
    bridge_status: BridgeStatus
    patient_id: uuid.UUID
    patient_name: str
    patient_age: int
    patient_blood_group: BloodGroup
    role: MembershipRole
    status: MembershipStatus
    joined_at: date


class DonorDetail(DonorListItem):
    """Full donor profile including their bridge memberships."""

    phone: str
    lat: float
    lng: float
    extended_phenotype: Optional[str]
    registered_at: datetime
    memberships: list[DonorBridgeMembership]


class DonorsPage(BaseModel):
    """Paginated donor list response."""

    items: list[DonorListItem]
    total: int
    skip: int
    limit: int
