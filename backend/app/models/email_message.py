"""EmailMessage — mirror of WhatsAppMessage for the SES email channel.

Email is a parallel outbound rail to WhatsApp. We track every send with the
same shape (recipient, body, template, status, provider SID) so the UI can
render WhatsApp + Email threads side-by-side and operators can audit who
got what when.

The model is intentionally similar to ``WhatsAppMessage`` so the same
analytics queries can union over both rails.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import GUID


class EmailMessage(Base):
    __tablename__ = "email_messages"
    __table_args__ = (
        Index("ix_email_messages_recipient", "recipient_email"),
        Index("ix_email_messages_template", "template_key"),
        Index("ix_email_messages_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    # Direction tracker — for parity with WhatsAppMessage, even though SES
    # is outbound-only today. Inbound (mail-to-webhook) is a future hook.
    direction: Mapped[str] = mapped_column(String(8), default="outbound")

    # Recipients
    recipient_email: Mapped[str] = mapped_column(String(254))
    from_email: Mapped[str] = mapped_column(String(254))

    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    template_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)

    # Provider metadata
    ses_message_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    # queued | sent | failed | mocked
    is_mock: Mapped[bool] = mapped_column(default=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Optional linkage to a donor or caregiver-for-patient — denormalised so
    # the analytics tile can group by recipient type without joins.
    donor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("donors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    caregiver_for_patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<EmailMessage to={self.recipient_email} template={self.template_key} "
            f"status={self.status}>"
        )
