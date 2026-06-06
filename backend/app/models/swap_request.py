"""SlotSwapRequest — G6 swap state machine.

Donor A asks (via WhatsApp inbound) to swap their slot with donor B in the
same bridge. A row is created in PROPOSED state and an outbound
`swap_request_inbound` template is fired at B. B's YES flips to ACCEPTED
and triggers an auto-resolve. B's NO flips to REJECTED and notifies A.
A row stays PROPOSED for 48h before lazy-expiry on read.
"""

from __future__ import annotations

import uuid
from datetime import date as date_t, datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import GUID


class SwapStatus(str, Enum):
    PROPOSED = "proposed"      # Donor A asked, donor B has not yet replied
    ACCEPTED = "accepted"      # B said YES — schedule should reflect the swap
    REJECTED = "rejected"      # B said NO — A's slot stays as-is
    EXPIRED = "expired"        # No reply within 48h
    CANCELLED = "cancelled"    # Reserved for coordinator-initiated cancel


class SlotSwapRequest(Base):
    """One swap proposal between two donors on the same bridge."""

    __tablename__ = "slot_swap_requests"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    bridge_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("bridges.id", ondelete="CASCADE"), index=True
    )
    from_donor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("donors.id", ondelete="CASCADE"), index=True
    )
    to_donor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("donors.id", ondelete="CASCADE"), index=True
    )
    from_slot_date: Mapped[date_t] = mapped_column(Date)
    to_slot_date: Mapped[date_t] = mapped_column(Date)

    status: Mapped[SwapStatus] = mapped_column(String(12), default=SwapStatus.PROPOSED, index=True)

    # 48h after PROPOSED — used by lazy expiry sweep.
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    # Twilio SID of the swap_request_inbound message to B.
    notify_message_sid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
