"""WhatsAppMessage entity — Phase 10 conversation log."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.types import GUID


class MessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus(str, Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    RECEIVED = "received"  # for inbound
    FAILED = "failed"
    MOCKED = "mocked"  # local-only echo in mock mode


class WhatsAppMessage(Base):
    """One message in a WhatsApp conversation with a donor."""

    __tablename__ = "whatsapp_messages"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    donor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("donors.id", ondelete="SET NULL"), nullable=True
    )
    bridge_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("bridges.id", ondelete="SET NULL"), nullable=True
    )
    # G5: caregiver-recipient messages have patient_id set + donor_id null.
    # Lets us group caregiver conversations by patient on the WhatsApp page.
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True
    )

    direction: Mapped[MessageDirection] = mapped_column(String(10))
    from_number: Mapped[str] = mapped_column(String(40))
    to_number: Mapped[str] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text)

    status: Mapped[MessageStatus] = mapped_column(String(15), default=MessageStatus.QUEUED)
    twilio_sid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    template_key: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # G4: what language this message was rendered in (or None for raw inbound).
    language: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Optional relationships (not required for the API to work)
    donor = relationship("Donor", lazy="joined", foreign_keys=[donor_id])
    bridge = relationship("Bridge", lazy="joined", foreign_keys=[bridge_id])

    def __repr__(self) -> str:
        return (
            f"<WhatsAppMessage {self.direction.value} {self.from_number}->"
            f"{self.to_number} status={self.status.value}>"
        )
