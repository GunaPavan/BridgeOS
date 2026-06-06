"""WhatsApp messaging schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BloodGroup


MessageDirectionLiteral = Literal["inbound", "outbound"]
MessageStatusLiteral = Literal[
    "queued", "sent", "delivered", "read", "received", "failed", "mocked"
]
LanguageLiteral = Literal["en", "hi", "te", "ta", "mr", "bn", "kn", "gu"]


class DonorSummaryRef(BaseModel):
    """Compact donor reference embedded in a conversation summary."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    blood_group: BloodGroup
    phone: str
    preferred_language: str
    city: str


class WhatsAppMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    donor_id: Optional[uuid.UUID]
    bridge_id: Optional[uuid.UUID]
    direction: MessageDirectionLiteral
    from_number: str
    to_number: str
    body: str
    status: MessageStatusLiteral
    twilio_sid: Optional[str]
    template_key: Optional[str]
    language: Optional[str] = None
    created_at: datetime


class CaregiverRef(BaseModel):
    """Caregiver (patient-side recipient) reference used by /whatsapp/conversations."""

    patient_id: uuid.UUID
    patient_name: str
    patient_blood_group: BloodGroup
    caregiver_name: str
    caregiver_relation: Optional[str] = None
    caregiver_phone: str


class ConversationSummary(BaseModel):
    """One conversation — either a donor thread or a caregiver thread (G5)."""

    kind: Literal["donor", "caregiver"] = "donor"
    donor: Optional[DonorSummaryRef] = None
    caregiver: Optional[CaregiverRef] = None
    last_message: WhatsAppMessageOut
    message_count: int


class ConversationsList(BaseModel):
    conversations: list[ConversationSummary]
    total: int


class ConversationThread(BaseModel):
    """A donor's thread. Caregiver threads use CaregiverConversationThread."""

    donor: DonorSummaryRef
    messages: list[WhatsAppMessageOut]


class CaregiverConversationThread(BaseModel):
    """All caregiver messages tied to one patient."""

    caregiver: CaregiverRef
    messages: list[WhatsAppMessageOut]


class SendMessageRequest(BaseModel):
    donor_id: uuid.UUID
    body: Optional[str] = Field(default=None, description="Free-form text. Required if template_key is None.")
    template_key: Optional[str] = Field(default=None, description="Use a preset template (key + variables filled server-side).")
    bridge_id: Optional[uuid.UUID] = None
    language: Optional[LanguageLiteral] = Field(
        default=None,
        description=(
            "Language code for template rendering. Defaults to the donor's "
            "preferred_language. Ignored for free-form `body`."
        ),
    )


class SendMessageResponse(BaseModel):
    message: WhatsAppMessageOut
    is_live_twilio: bool
    language_used: Optional[LanguageLiteral] = Field(
        default=None,
        description="Language the template was actually rendered in (may differ from request if English fallback was used).",
    )
    fallback_used: bool = Field(
        default=False,
        description="True when the requested language had no hand-authored body and we fell back to English.",
    )


class TwilioStatusInfo(BaseModel):
    is_live: bool
    from_number: str
    sandbox_join_instructions: str = Field(
        description="Plain-English instructions a coordinator can paste to a donor"
    )


class MessageTemplate(BaseModel):
    """Template definition with multilingual bodies (G4)."""

    key: str
    label: str
    requires_bridge: bool = False
    bodies: dict[str, str] = Field(
        default_factory=dict,
        description="Hand-authored body per language code (en, hi, te, ta, mr, bn, kn, gu).",
    )
    supported_languages: list[str] = Field(
        default_factory=list,
        description="Subset of language codes that have a non-empty body.",
    )
