"""Recommendation + recruitment schemas."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BloodGroup, BridgeHealth
from app.schemas.donor import DonorSummary
from app.schemas.stability import StabilityFactor


UrgencyLiteral = Literal["critical", "high", "medium"]


class CandidateRationaleOut(BaseModel):
    factor: str
    value: float
    description: str


class CandidateOut(BaseModel):
    donor: DonorSummary
    composite_score: float = Field(ge=0.0, le=1.0)
    distance_km: float
    predicted_churn_90d: float = Field(ge=0.0, le=1.0)
    days_until_eligible: int = Field(ge=0)
    rationale: list[CandidateRationaleOut]


class WeakDonorOut(BaseModel):
    membership_id: uuid.UUID
    donor_id: uuid.UUID
    donor_name: str
    role: str
    churn_90d: float = Field(ge=0.0, le=1.0)
    top_factors: list[StabilityFactor]


class BridgeRecommendationOut(BaseModel):
    bridge_id: uuid.UUID
    bridge_name: str
    patient_id: uuid.UUID
    patient_name: str
    patient_age: int
    patient_blood_group: BloodGroup
    patient_hospital: str
    patient_city: str
    bridge_health_stub: BridgeHealth = Field(
        description="Phase 1 count-based health (kept for backward compat)"
    )
    active_donor_count: int
    urgency: UrgencyLiteral
    weak_donors: list[WeakDonorOut]
    candidates: list[CandidateOut]


class RecommendationsInbox(BaseModel):
    items: list[BridgeRecommendationOut]
    total: int


LanguageLiteral = Literal["en", "hi", "te", "ta", "mr", "bn", "kn", "gu"]


class RecruitRequest(BaseModel):
    candidate_donor_id: uuid.UUID
    replace_donor_id: Optional[uuid.UUID] = Field(
        default=None,
        description=(
            "If provided, this donor is the one being swapped out. Their "
            "membership stays ACTIVE during the pending window and only flips "
            "to EXITED when the candidate replies YES."
        ),
    )
    language: Optional[LanguageLiteral] = Field(
        default=None,
        description=(
            "Language for the WhatsApp recruit_invite. Defaults to the donor's "
            "preferred_language."
        ),
    )
    notes: Optional[str] = None


class RecruitResponse(BaseModel):
    bridge_id: uuid.UUID
    added_membership_id: uuid.UUID
    added_donor_id: uuid.UUID
    added_donor_name: str
    status: Literal["pending", "active"] = Field(
        default="pending",
        description=(
            "G1: recruits now start PENDING and require donor YES via WhatsApp. "
            "Stays 'pending' until the inbound webhook confirms."
        ),
    )
    waiting_for_donor_reply: bool = Field(
        default=True,
        description="True while PENDING; flips to False on YES (membership becomes ACTIVE) or NO (REJECTED).",
    )
    message_sid: Optional[str] = Field(
        default=None,
        description="Twilio SID (or MOCK… SID in mock mode) of the recruit_invite WhatsApp message.",
    )
    message_language: Optional[LanguageLiteral] = None
    replace_donor_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Donor scheduled to be swapped out when the candidate replies YES.",
    )
    new_active_donor_count: int = Field(
        description=(
            "Active donor count *right now* — does NOT yet include the PENDING "
            "candidate and DOES still include the donor pending replacement."
        ),
    )
    message: str


class PendingRecruitOut(BaseModel):
    """One PENDING membership awaiting a WhatsApp YES/NO."""

    model_config = ConfigDict(from_attributes=True)

    membership_id: uuid.UUID
    bridge_id: uuid.UUID
    candidate_donor_id: uuid.UUID
    candidate_donor_name: str
    candidate_donor_phone: str
    candidate_donor_language: str
    replaces_donor_id: Optional[uuid.UUID]
    replaces_donor_name: Optional[str]
    invite_message_sid: Optional[str]
    invite_language: Optional[str]
    joined_at: date


class PendingActionOut(BaseModel):
    """A pending action a donor can ACCEPT / DECLINE — surfaces what a YES on WhatsApp will do."""

    kind: Literal["recruit"]
    membership_id: uuid.UUID
    bridge_id: uuid.UUID
    bridge_name: str
    patient_name: str
    replaces_donor_name: Optional[str]
    invite_sent_at: Optional[date]
