"""Bridge and BridgeMembership — the cohort that ties one patient to ~10 donors."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import (
    BridgeHealth,
    BridgeStatus,
    MembershipRole,
    MembershipStatus,
)
from app.models.types import GUID

if TYPE_CHECKING:
    from app.models.donor import Donor
    from app.models.patient import Patient


# Clinical floor for donor-deferral math (90-day inter-donation window).
DONOR_DEFERRAL_DAYS = 90
# Cadence we assume when patient.transfusion_cadence_days is missing.
_DEFAULT_PATIENT_CADENCE = 21


def min_active_donors_required(patient_cadence_days: Optional[int]) -> int:
    """Number of independent active donors needed to sustain one patient
    on a given transfusion cadence, given the 90-day donor deferral.

    ``ceil(90 / cadence)``. A patient on 21-day cadence needs ≥5 donors;
    a 14-day cadence patient needs ≥7; a 30-day cadence patient needs ≥3.

    Returns at least 2 so we never claim a single-donor cohort is sustainable.
    """
    cad = patient_cadence_days if patient_cadence_days and patient_cadence_days > 0 else _DEFAULT_PATIENT_CADENCE
    return max(2, (DONOR_DEFERRAL_DAYS + cad - 1) // cad)


def bridge_health_from_headcount(
    active_donor_count: int,
    patient_cadence_days: Optional[int],
) -> "BridgeHealth":
    """Cadence-aware bridge-health classifier (single source of truth).

    STABLE  — active donors ≥ ⌈1.5 × clinical minimum⌉ (healthy buffer for
              absences and refusals)
    AT_RISK — active donors ≥ clinical minimum (just covered, no slack)
    CRITICAL — active donors < clinical minimum (cannot sustain cycle)
    """
    min_required = min_active_donors_required(patient_cadence_days)
    stable_threshold = max(min_required + 1, (min_required * 3 + 1) // 2)
    if active_donor_count >= stable_threshold:
        return BridgeHealth.STABLE
    if active_donor_count >= min_required:
        return BridgeHealth.AT_RISK
    return BridgeHealth.CRITICAL


class Bridge(Base):
    """A Blood Bridge: one patient and the rotating cohort of donors that sustains them."""

    __tablename__ = "bridges"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("patients.id", ondelete="CASCADE"), unique=True
    )
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[BridgeStatus] = mapped_column(String(10), default=BridgeStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    patient: Mapped["Patient"] = relationship(back_populates="bridge")
    memberships: Mapped[list["BridgeMembership"]] = relationship(
        back_populates="bridge",
        cascade="all, delete-orphan",
        order_by="BridgeMembership.joined_at",
    )

    # --- Derived ---

    @property
    def active_donor_count(self) -> int:
        return sum(1 for m in self.memberships if m.status == MembershipStatus.ACTIVE)

    @property
    def total_donor_count(self) -> int:
        return len(self.memberships)

    @property
    def patient_cadence_days(self) -> Optional[int]:
        try:
            return self.patient.transfusion_cadence_days if self.patient else None
        except Exception:
            return None

    @property
    def health(self) -> BridgeHealth:
        """Cadence-aware classifier (delegates to ``bridge_health_from_headcount``).

        See ``bridge_health_from_headcount`` for the rule. The thresholds scale
        per-patient based on transfusion cadence vs the 90-day donor deferral.
        """
        return bridge_health_from_headcount(
            self.active_donor_count, self.patient_cadence_days
        )

    def __repr__(self) -> str:
        return f"<Bridge {self.name} ({self.active_donor_count} donors, {self.health.value})>"


class BridgeMembership(Base):
    """A donor's membership in a specific bridge."""

    __tablename__ = "bridge_memberships"
    __table_args__ = (
        UniqueConstraint("bridge_id", "donor_id", name="uq_membership_bridge_donor"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    bridge_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("bridges.id", ondelete="CASCADE")
    )
    donor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("donors.id", ondelete="CASCADE")
    )

    role: Mapped[MembershipRole] = mapped_column(String(10), default=MembershipRole.PRIMARY)
    status: Mapped[MembershipStatus] = mapped_column(String(10), default=MembershipStatus.ACTIVE)
    joined_at: Mapped[date] = mapped_column(default=date.today)
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # G1: when this row is PENDING and was created to replace a current donor,
    # this points at the donor the coordinator intends to swap out. The old
    # member stays ACTIVE during the pending window and only flips to EXITED
    # when (or if) this PENDING row flips to ACTIVE on the donor's YES reply.
    replaces_donor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("donors.id", ondelete="SET NULL"), nullable=True
    )

    # Provenance for the WhatsApp consent message — useful for debugging
    # and for the /pending-recruits panel.
    invite_message_sid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    invite_language: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)

    # Relationships
    bridge: Mapped["Bridge"] = relationship(back_populates="memberships")
    donor: Mapped["Donor"] = relationship(
        back_populates="memberships", foreign_keys=[donor_id]
    )

    def __repr__(self) -> str:
        status_val = getattr(self.status, "value", str(self.status))
        return f"<Membership donor={self.donor_id} bridge={self.bridge_id} {status_val}>"
