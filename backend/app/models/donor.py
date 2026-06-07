"""Donor entity — a voluntary blood donor."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import (
    BloodGroup,
    ContactChannel,
    DonorType,
    Gender,
    InactiveReason,
    Language,
)
from app.models.types import GUID

if TYPE_CHECKING:
    from app.models.bridge import BridgeMembership


class Donor(Base):
    """A voluntary blood donor in the Bridge OS network."""

    __tablename__ = "donors"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # CSV ``user_id`` from the Blood Warriors dataset — kept so the UI can
    # display a short 6-char handle (e.g. ``A72875``) next to the name and so
    # operators can cross-reference Bridge OS with the source spreadsheet.
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    age: Mapped[int] = mapped_column(Integer)

    # Clinical
    blood_group: Mapped[BloodGroup] = mapped_column(String(3))
    rh_negative: Mapped[bool] = mapped_column(Boolean, default=False)
    kell_negative: Mapped[bool] = mapped_column(Boolean, default=False)
    extended_phenotype: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Contact
    phone: Mapped[str] = mapped_column(String(20))
    # E14.B: donor's email used to link Cognito account → Donor row.
    # Optional because legacy seed donors don't have one; admin can set it
    # when the donor signs up via the hosted UI.
    email: Mapped[Optional[str]] = mapped_column(String(254), nullable=True, index=True)
    preferred_language: Mapped[Language] = mapped_column(String(2), default=Language.ENGLISH)
    # E6: per-donor outbound channel preference. Default = WHATSAPP because
    # it's the only channel where donor replies feed back into the automation
    # loop (Twilio webhook → classify → cooldown / re-fire). SMS via SNS is
    # one-way only (AWS doesn't offer free inbound India SMS — DLT takes
    # weeks). So SMS is opt-in only, as an emergency push channel.
    preferred_channel: Mapped[ContactChannel] = mapped_column(
        String(20), default=ContactChannel.WHATSAPP, nullable=False
    )

    # Geography
    city: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(80))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)

    # Donation history (denormalized for Phase 1; Donation entity arrives in Phase 4)
    last_donation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    total_donations: Mapped[int] = mapped_column(Integer, default=0)

    # Behavioral signal (used by Phase 4 stability model)
    response_rate: Mapped[float] = mapped_column(Float, default=1.0)
    avg_response_hours: Mapped[float] = mapped_column(Float, default=4.0)

    # --- Real-data fields from Blood Warriors dataset ---
    # Type of donor: ONE_TIME (emergency-only), REGULAR (bridge participant), OTHER
    donor_type: Mapped[Optional[DonorType]] = mapped_column(String(20), nullable=True)
    # Reason for inactivity — null if currently active
    inactive_reason: Mapped[Optional[InactiveReason]] = mapped_column(String(30), nullable=True)
    # Coordinator outreach history (from total_calls column)
    total_calls: Mapped[int] = mapped_column(Integer, default=0)
    # Outreach efficiency = total_calls / donations_till_date (lower = better)
    calls_to_donations_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    # Empirical donation cycle length (days between donations)
    avg_cycle_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Whether the donor has ever donated (true if total_donations >= 1)
    donated_earlier: Mapped[bool] = mapped_column(Boolean, default=False)
    # When the donor was last contacted by a coordinator
    last_contacted_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Gender (often unknown for Guest pool)
    gender: Mapped[Optional[Gender]] = mapped_column(String(10), nullable=True)

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships — must specify foreign_keys because BridgeMembership now
    # has two FKs to donors (donor_id and replaces_donor_id).
    memberships: Mapped[list["BridgeMembership"]] = relationship(
        back_populates="donor",
        cascade="all, delete-orphan",
        foreign_keys="BridgeMembership.donor_id",
    )

    # --- Derived ---

    @property
    def days_since_donation(self) -> Optional[int]:
        """Days since this donor's last donation, anchored to the dataset clock.

        See ``app.system_clock`` — wall-clock 'today' on stale snapshot data
        produces nonsensical hundreds-of-days values; the anchored clock
        keeps the field meaningful.
        """
        if not self.last_donation_date:
            return None
        from app.system_clock import today as _today
        return (_today() - self.last_donation_date).days

    @property
    def is_eligible_to_donate(self) -> bool:
        """Eligible if active and at least 90 days past last donation.

        Uses wall-clock today rather than the dataset-anchored clock — the
        donor's body recovers in real time, so eligibility is a real-time
        clinical state regardless of when the snapshot was taken.
        """
        if not self.is_active:
            return False
        if self.last_donation_date is None:
            return True
        days_since = (date.today() - self.last_donation_date).days
        return days_since >= 90

    def __repr__(self) -> str:
        return f"<Donor {self.name} ({self.blood_group})>"
