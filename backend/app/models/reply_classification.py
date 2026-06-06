"""ReplyClassification — audit log + training feedback loop for the
Bedrock-powered inbound reply interpreter.

Every inbound WhatsApp message that the classifier runs against produces
ONE row in this table. The classifier writes:

  - the intent it picked + its confidence
  - any structured data it extracted (dates for reschedule, reason for
    decline)
  - the raw text excerpt (200 chars max, for review without privacy bloat)
  - the model id used (for A/B comparisons later)

Coordinators can then call ``POST /reply-classifications/{id}/feedback``
to mark a wrong call — that populates ``operator_corrected_intent`` and
gives us a clean training set for future fine-tuning runs.

``deleted_at`` is a soft-delete flag — privacy/right-to-be-forgotten
deletes go through this column so we keep referential integrity with
``WhatsAppMessage`` while hiding the row from API queries.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import DateTime, Date, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import ReplyIntent
from app.models.types import GUID


class ReplyClassification(Base):
    """One row per inbound message that the classifier processed."""

    __tablename__ = "reply_classifications"
    __table_args__ = (
        # Composite for the by-donor history query; per-column indexes below
        # via column index=True attribute (intent, classified_at, donor_id).
        Index("ix_reply_classifications_donor_classified", "donor_id", "classified_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    # Source attribution. message_id is the WhatsAppMessage row this
    # classification was computed for; donor_id is denormalised for fast
    # per-donor queries.
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("whatsapp_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    donor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("donors.id", ondelete="CASCADE"), index=True
    )

    # 200 chars is plenty for review — full body lives on WhatsAppMessage.
    text_excerpt: Mapped[str] = mapped_column(String(200))
    language: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)

    # The classifier's output.
    intent: Mapped[ReplyIntent] = mapped_column(String(24), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    extracted_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    extracted_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Provenance
    model_used: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    raw_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    used_fallback: Mapped[bool] = mapped_column(default=False)

    classified_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)

    # Feedback loop
    operator_corrected_intent: Mapped[Optional[ReplyIntent]] = mapped_column(
        String(24), nullable=True
    )
    operator_feedback_note: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    feedback_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Soft delete
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    def __repr__(self) -> str:
        return (
            f"<ReplyClassification donor={self.donor_id} intent={self.intent} "
            f"conf={self.confidence:.2f} {'corrected' if self.operator_corrected_intent else ''}>"
        )
