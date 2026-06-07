"""Patient entity — a thalassemia patient on a Blood Bridge."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import (
    BloodGroup,
    CaregiverRelation,
    ContactChannel,
    Gender,
    Language,
)
from app.models.types import GUID

if TYPE_CHECKING:
    from app.models.bridge import Bridge


class Patient(Base):
    """Thalassemia patient who needs recurring transfusions."""

    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # CSV ``user_id`` from the Blood Warriors dataset — kept so the UI can
    # display a short 6-char handle (e.g. ``A72875``) next to the name and so
    # operators can cross-reference Bridge OS with the source spreadsheet.
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    age: Mapped[int] = mapped_column(Integer)

    # Clinical
    # String(10) — see donor.py for the same fix. ABO/Rh codes ≤ 3 chars but
    # the BloodGroup enum also has 'Bombay' (6) and 'unknown' (7) for guest-
    # pool donors/patients sourced from the Blood Warriors CSV.
    blood_group: Mapped[BloodGroup] = mapped_column(String(10))
    rh_negative: Mapped[bool] = mapped_column(Boolean, default=False)
    kell_negative: Mapped[bool] = mapped_column(Boolean, default=False)
    extended_phenotype: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Geography
    city: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(80))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    hospital: Mapped[str] = mapped_column(String(160))

    # Transfusion plan
    transfusion_cadence_days: Mapped[int] = mapped_column(Integer, default=18)
    last_transfusion_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    preferred_language: Mapped[Language] = mapped_column(String(2), default=Language.ENGLISH)

    # --- Real-data fields from Blood Warriors dataset ---
    # How many units per transfusion this patient needs (from quantity_required)
    units_per_transfusion: Mapped[int] = mapped_column(Integer, default=1)
    # Patient gender
    gender: Mapped[Optional[Gender]] = mapped_column(String(10), nullable=True)

    # Caregiver — the person who receives WhatsApp updates about this patient (G5).
    # For self-managing adult patients, set caregiver_name = patient.name and
    # caregiver_relation = SELF; caregiver_phone may equal patient's own phone.
    caregiver_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    caregiver_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Phase E2: email fallback channel — used by SES daily digests + emergency
    # alerts when WhatsApp delivery fails. Optional; daily digest job skips
    # patients without an email on file.
    caregiver_email: Mapped[Optional[str]] = mapped_column(String(254), nullable=True)
    caregiver_relation: Mapped[Optional[CaregiverRelation]] = mapped_column(
        String(10), nullable=True
    )
    # E6: caregiver channel preference. Default WHATSAPP because caregivers
    # tend to be parents/family with smartphones — they want rich messages,
    # multi-language support, and two-way replies. SMS fallback if no app.
    caregiver_preferred_channel: Mapped[ContactChannel] = mapped_column(
        String(20), default=ContactChannel.WHATSAPP, nullable=False
    )

    # Lifecycle
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    bridge: Mapped[Optional["Bridge"]] = relationship(
        back_populates="patient", uselist=False, cascade="all, delete-orphan"
    )

    # --- Derived ---

    @property
    def next_transfusion_date(self) -> Optional[date]:
        if not self.last_transfusion_date:
            return None
        return self.last_transfusion_date + timedelta(days=self.transfusion_cadence_days)

    @property
    def days_until_transfusion(self) -> Optional[int]:
        """Days until the next scheduled transfusion.

        Uses ``app.system_clock.today()`` rather than wall-clock — the
        dataset is a snapshot, so wall-clock "now" can be months ahead and
        produces meaningless 200-day-overdue values. The dataset-anchored
        clock keeps the field truthful relative to the data on hand.

        Returns None for snapshot-stale records (scheduled date is more than
        ``STALE_THRESHOLD_DAYS`` in the past relative to the anchored clock)
        — there's no clinical meaning in saying a patient is "60 days
        overdue" when the data was captured at an unknown point earlier
        and they may have already had the transfusion at another centre.
        """
        nt = self.next_transfusion_date
        if nt is None:
            return None
        from app.system_clock import today as _today
        delta = (nt - _today()).days
        # If a transfusion was scheduled more than ~30 days ago relative to
        # the dataset's own reference, treat it as stale (snapshot
        # artifact) and return None so callers don't render alarming numbers.
        STALE_THRESHOLD_DAYS = 30
        if delta < -STALE_THRESHOLD_DAYS:
            return None
        return delta

    def __repr__(self) -> str:
        return f"<Patient {self.name} ({self.blood_group}) age {self.age}>"
