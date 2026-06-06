"""Pydantic schemas for the /reply-classifications/* API surface."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ReplyIntent


# ---------------------------------------------------------------------------
# Read shapes
# ---------------------------------------------------------------------------


class ReplyClassificationOut(BaseModel):
    """Compact row for the list views."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    donor_id: uuid.UUID
    message_id: Optional[uuid.UUID] = None
    text_excerpt: str
    language: Optional[str] = None
    intent: ReplyIntent
    confidence: float
    extracted_date: Optional[date] = None
    extracted_reason: Optional[str] = None
    model_used: Optional[str] = None
    used_fallback: bool = False
    classified_at: datetime
    operator_corrected_intent: Optional[ReplyIntent] = None
    operator_feedback_note: Optional[str] = None
    feedback_at: Optional[datetime] = None


class ReplyClassificationDetail(ReplyClassificationOut):
    """Full row including the raw model JSON response."""

    raw_response: Optional[str] = None


class ReplyClassificationsPage(BaseModel):
    items: list[ReplyClassificationOut]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    """Operator corrects the classifier's intent for one row.

    Pass ``corrected_intent=None`` to clear a previous correction.
    """

    corrected_intent: Optional[ReplyIntent] = Field(
        default=None,
        description="The intent the operator thinks is correct. None to clear.",
    )
    note: Optional[str] = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class IntentCount(BaseModel):
    intent: ReplyIntent
    count: int


class IntentDistribution(BaseModel):
    window_days: int
    total: int
    counts: list[IntentCount]
    avg_confidence: float
    fallback_rate: float
    top_reschedule_reasons: list[str] = Field(default_factory=list)


class ConfidenceBucket(BaseModel):
    """One slice of the confidence histogram (e.g. 0.6-0.7 → N rows)."""

    low: float
    high: float
    count: int
