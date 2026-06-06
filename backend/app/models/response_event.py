"""DonorResponseEvent — one row per EMA bump (G2 feedback loop).

Each event records:
    - what happened (REPLY / NO_REPLY)
    - the prior/new response_rate so a sparkline can replay the curve
    - the WhatsApp message it was responding to (or marking unanswered)
    - the hours-to-reply when the event is a REPLY

`/donors/{id}/response-history` reads this table to draw the 30-day sparkline.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import GUID


class ResponseEventKind(str, Enum):
    REPLY = "reply"            # donor replied to an outbound — bumps EMA up
    NO_REPLY = "no_reply"      # outbound aged past the 48h window unanswered — decays EMA down


class DonorResponseEvent(Base):
    """One EMA bump on a donor's response stats."""

    __tablename__ = "donor_response_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    donor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("donors.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ResponseEventKind] = mapped_column(String(10))

    # The outbound this event scores (the message they replied to, or the one
    # we're marking unanswered). Nullable for unsolicited inbounds.
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("whatsapp_messages.id", ondelete="SET NULL"), nullable=True
    )

    # Hours between the outbound and the inbound (REPLY only).
    hours_to_response: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # EMA before and after this event — lets the UI replay the curve without
    # re-running the math.
    prior_response_rate: Mapped[float] = mapped_column(Float)
    new_response_rate: Mapped[float] = mapped_column(Float)
    prior_avg_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_avg_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
