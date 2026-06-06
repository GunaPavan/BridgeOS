"""Patient schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import BloodGroup, BridgeHealth, BridgeStatus, Language


class PatientDetail(BaseModel):
    """Full patient profile used inside BridgeDetail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_handle: Optional[str] = None
    name: str
    age: int
    blood_group: BloodGroup
    rh_negative: bool
    kell_negative: bool
    extended_phenotype: Optional[str]
    city: str
    state: str
    hospital: str
    transfusion_cadence_days: int
    last_transfusion_date: Optional[date]
    preferred_language: Language
    active: bool


class PatientBridgeRef(BaseModel):
    """Bridge summary embedded in a patient profile."""

    bridge_id: uuid.UUID
    bridge_name: str
    bridge_status: BridgeStatus
    active_donor_count: int
    total_donor_count: int
    health: BridgeHealth
    created_at: datetime


class PatientListItem(BaseModel):
    """Patient row for the /patients list view."""

    id: uuid.UUID
    external_handle: Optional[str] = None  # 6-char chip derived from CSV user_id
    name: str
    age: int
    blood_group: BloodGroup
    rh_negative: bool
    kell_negative: bool
    city: str
    state: str
    hospital: str
    preferred_language: Language

    transfusion_cadence_days: int
    last_transfusion_date: Optional[date]
    next_transfusion_date: Optional[date]
    days_until_transfusion: Optional[int]

    active: bool
    has_bridge: bool
    bridge_health: Optional[BridgeHealth]
    active_donor_count: int


class PatientProfile(PatientListItem):
    """Full patient profile including bridge summary and projected transfusions."""

    extended_phenotype: Optional[str]
    lat: float
    lng: float
    registered_at: datetime
    bridge: Optional[PatientBridgeRef]
    projected_transfusions: list[date]
    # G5
    caregiver_name: Optional[str] = None
    caregiver_phone: Optional[str] = None
    caregiver_relation: Optional[str] = None


class PatientsPage(BaseModel):
    """Paginated patient list response."""

    items: list[PatientListItem]
    total: int
    skip: int
    limit: int
