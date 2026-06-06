"""Pydantic schemas for the /emails/* API surface."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EmailMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    direction: str
    recipient_email: str
    from_email: str
    subject: str
    body: str
    template_key: Optional[str] = None
    language: Optional[str] = None
    ses_message_id: Optional[str] = None
    status: str
    is_mock: bool
    error_message: Optional[str] = None
    donor_id: Optional[uuid.UUID] = None
    caregiver_for_patient_id: Optional[uuid.UUID] = None
    created_at: datetime
    sent_at: Optional[datetime] = None


class EmailMessagesPage(BaseModel):
    items: list[EmailMessageOut]
    total: int
    limit: int
    offset: int


class EmailTemplateCount(BaseModel):
    template_key: str
    sent: int = 0
    failed: int = 0
    mocked: int = 0
    skipped: int = 0


class EmailDistribution(BaseModel):
    window_days: int
    total: int
    sent: int
    failed: int
    mocked: int
    by_template: list[EmailTemplateCount]


class TestEmailRequest(BaseModel):
    recipient: EmailStr
    subject: str = Field(default="Bridge OS test", max_length=200)
    body: str = Field(
        default="If you're reading this, SES is wired up correctly. 🎉",
        max_length=2000,
    )


class TestEmailResponse(BaseModel):
    message_id: str
    is_mock: bool
    status: str
    persisted_id: uuid.UUID


class VerifyIdentityRequest(BaseModel):
    email: EmailStr
