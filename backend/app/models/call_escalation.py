"""E11 — call escalation model.

When an OutreachWave goes past its urgency-tier threshold without any
ping being accepted, the auto-escalation job creates a CallEscalation
row + dispatches an alert to the coordinator.

EscalationStatus lifecycle:
    PENDING   → just created, waiting for dispatch
    DISPATCHED → SMS/voice call sent to coordinator
    ACKED     → coordinator clicked "ack" in the UI
    RESOLVED  → wave was eventually filled (or expired) — closes the loop
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.types import GUID

if TYPE_CHECKING:
    from app.models.outreach import OutreachWave
    from app.models.patient import Patient


class EscalationStatus(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    ACKED = "acked"
    RESOLVED = "resolved"


class EscalationChannel(str, Enum):
    """How we tried to reach the coordinator."""

    SMS = "sms"          # SNS direct SMS
    VOICE = "voice"      # Twilio Voice auto-call
    SMS_AND_VOICE = "sms_and_voice"


class CallEscalation(Base):
    """One escalation event per (wave, urgency-trigger). One wave can have
    multiple escalations if it gets re-escalated after acknowledgement."""

    __tablename__ = "call_escalations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    wave_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("outreach_waves.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("patients.id"), nullable=False, index=True
    )

    # Threshold tracking — useful for auditing "why did we escalate now"
    urgency_at_trigger: Mapped[str] = mapped_column(String(12))
    hours_since_dispatch: Mapped[int] = mapped_column(Integer)
    pings_sent: Mapped[int] = mapped_column(Integer, default=0)
    pings_no_response: Mapped[int] = mapped_column(Integer, default=0)

    # Coordinator contact target
    coordinator_phone: Mapped[str] = mapped_column(String(20))

    status: Mapped[EscalationStatus] = mapped_column(
        String(12), default=EscalationStatus.PENDING, index=True
    )
    channel: Mapped[Optional[EscalationChannel]] = mapped_column(
        String(20), nullable=True
    )

    # IDs from the actual dispatch
    sms_message_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    voice_call_sid: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Lifecycle timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ack_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    # Relationships
    wave: Mapped["OutreachWave"] = relationship()
    patient: Mapped["Patient"] = relationship()
