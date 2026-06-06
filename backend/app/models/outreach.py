"""Alert Allocator entities — waves, pings, emergency events.

These tables are the persistent state of the outreach engine:

    Patient slot at risk
      │
      ▼
    OutreachWave  ── tier, urgency, target P_accept, gap_days, status
      │
      └── OutreachPing × N   (one per donor we asked, channel + response state)
              │
              └── on expiry → escalate_wave_to_next_tier creates a fresh
                              wave on the next tier (TIER_1→TIER_2→TIER_3
                              →TIER_4_EXTERNAL). No human-in-the-loop tier.

    Coordinator hits the red button
      │
      ▼
    EmergencyEvent  ── hospital, deadline, reach_window, audit metadata
      │
      └── spins its own wave (tier = EMERGENCY) under the same allocator engine

    OutreachCooldown ── per (donor, patient?) — protects donors from being
                        burnt out by repeat asks. Two-tier:
                          DECLINED          → 30d for this patient only
                          NO_REPLY          → 7d across all patients
                          RECENT_DONATION   → 90d clinical (always honoured,
                                              even in EMERGENCY)
                          OPT_OUT_TEMPORARY → coordinator/donor-set window

All persistent state behind the allocator lives here. Pure compute lives in
``app.outreach.scoring`` and ``app.outreach.engine``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import (
    CooldownReason,
    EmergencyEventStatus,
    OutreachChannel,
    OutreachTier,
    OutreachWaveStatus,
    PingResponse,
    UrgencyTier,
)
from app.models.types import GUID

if TYPE_CHECKING:
    from app.models.bridge import Bridge
    from app.models.donor import Donor
    from app.models.patient import Patient


class OutreachWave(Base):
    """One escalation round of outreach for one patient slot."""

    __tablename__ = "outreach_waves"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    bridge_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("bridges.id", ondelete="SET NULL"), nullable=True, index=True
    )

    slot_date: Mapped[date] = mapped_column(index=True)

    tier: Mapped[OutreachTier] = mapped_column(String(24), default=OutreachTier.TIER_1)
    urgency: Mapped[UrgencyTier] = mapped_column(String(12), default=UrgencyTier.MEDIUM)
    status: Mapped[OutreachWaveStatus] = mapped_column(
        String(12), default=OutreachWaveStatus.ACTIVE
    )

    # Math snapshot for analytics / debugging
    target_p_accept: Mapped[float] = mapped_column(Float, default=0.85)
    realised_p_accept: Mapped[float] = mapped_column(Float, default=0.0)
    gap_days_at_creation: Mapped[int] = mapped_column(Integer, default=0)
    pool_size_at_creation: Mapped[int] = mapped_column(Integer, default=0)

    triggered_by: Mapped[str] = mapped_column(
        String(32), default="auto_cycle",
        # 'auto_cycle' | 'event_destabilise' | 'coordinator_manual' | 'emergency_button'
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_by_donor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("donors.id", ondelete="SET NULL"), nullable=True
    )

    # --- relationships ---
    pings: Mapped[list["OutreachPing"]] = relationship(
        back_populates="wave",
        cascade="all, delete-orphan",
        order_by="OutreachPing.sent_at",
    )

    def __repr__(self) -> str:
        return (
            f"<OutreachWave patient={self.patient_id} tier={self.tier} "
            f"urgency={self.urgency} status={self.status}>"
        )


class OutreachPing(Base):
    """A single outreach attempt to one donor in one wave."""

    __tablename__ = "outreach_pings"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    wave_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("outreach_waves.id", ondelete="CASCADE"), index=True
    )
    donor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("donors.id", ondelete="CASCADE"), index=True
    )

    channel: Mapped[OutreachChannel] = mapped_column(
        String(10), default=OutreachChannel.WHATSAPP
    )
    response: Mapped[PingResponse] = mapped_column(String(10), default=PingResponse.PENDING)

    sent_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    response_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # The template we rendered (so the webhook can match acceptances back to the
    # right (donor, wave) pair via the slot_id token).
    template_key: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    whatsapp_sid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Scoring snapshot at send time — useful for retrospective analysis
    composite_score: Mapped[float] = mapped_column(Float, default=0.0)
    adjusted_response_rate: Mapped[float] = mapped_column(
        Float, default=0.0,
        # response_rate * (1 - churn_90d) — the r_i used in the P_accept formula
    )

    # --- Phase B follow-up tracking ---
    # The automation engine ticks three follow-up jobs against pings:
    #   1. PENDING > 4h → ``auto_pending_nudge`` sends a softer reminder, up
    #      to ``MAX_NUDGES`` times with a ``MIN_NUDGE_GAP_HOURS`` cooldown
    #      between sends.
    #   2. ACCEPTED + slot tomorrow → ``auto_pre_donation_reminder`` sends a
    #      day-before commitment reminder. Fires once per ping.
    #   3. Donation confirmed (response=ACCEPTED + slot_date <= today) →
    #      ``auto_post_donation_thank_you`` thanks the donor and shares
    #      their next eligible date. Fires once per ping.
    # All three jobs check these stamps as their idempotency guard so
    # multiple ticks of the same job never double-send.
    nudge_count: Mapped[int] = mapped_column(Integer, default=0)
    last_nudge_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    thank_you_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # --- relationships ---
    wave: Mapped["OutreachWave"] = relationship(back_populates="pings")

    def __repr__(self) -> str:
        return (
            f"<OutreachPing wave={self.wave_id} donor={self.donor_id} "
            f"channel={self.channel} response={self.response}>"
        )


class EmergencyEvent(Base):
    """Audit + state for one coordinator-triggered emergency outreach."""

    __tablename__ = "emergency_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    patient_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )

    triggered_by: Mapped[str] = mapped_column(String(128))  # coordinator id/name
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    hospital_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hospital_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hospital_lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    transfusion_deadline_at: Mapped[datetime] = mapped_column(DateTime)
    reach_window_min: Mapped[int] = mapped_column(Integer, default=120)
    justification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    pool_size_at_trigger: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[EmergencyEventStatus] = mapped_column(
        String(12), default=EmergencyEventStatus.ACTIVE
    )

    # If a donor accepted (whatsapp OR phone), track them here
    accepted_donor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("donors.id", ondelete="SET NULL"), nullable=True
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Pointer to the OutreachWave the emergency spawned (so we share the same
    # wave/ping machinery instead of building a parallel mechanism)
    wave_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("outreach_waves.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<EmergencyEvent patient={self.patient_id} "
            f"status={self.status} deadline={self.transfusion_deadline_at}>"
        )


class OutreachCooldown(Base):
    """Per (donor, patient?) cooldown row — controls re-ask cadence.

    ``patient_id`` is nullable: when NULL the cooldown applies to every
    patient (e.g. NO_REPLY across the board, or a temporary opt-out). When
    set, the cooldown applies only to that specific (donor, patient) pair
    so the donor remains eligible for other patients.

    Cooldowns are honoured by the allocator's eligibility filter EXCEPT in
    EMERGENCY tier where social cooldowns are waived (clinical 90-day
    deferral is still honoured — it's stored on the donor row, not here).
    """

    __tablename__ = "outreach_cooldowns"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    donor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("donors.id", ondelete="CASCADE"), index=True
    )
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("patients.id", ondelete="CASCADE"), nullable=True, index=True
    )

    reason: Mapped[CooldownReason] = mapped_column(String(24))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Free-text trail (e.g. "declined invitation on 2026-05-12 wave abc-123")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<OutreachCooldown donor={self.donor_id} patient={self.patient_id} "
            f"reason={self.reason} expires={self.expires_at}>"
        )
