"""Feature extraction for the survival model.

Survival framing:
    duration  = days from last_donation_date (or registered_at if never donated)
                to (today if Active, or last_donation+365 if Inactive_NotDonated1Y,
                 or current snapshot if otherwise Inactive).
    event     = 1 if Inactive, 0 if Active (censored).

Features mirror the churn model but skew toward TIME-INVARIANT donor traits
(blood_group_known, is_regular, etc.) plus TENURE (days_since_registration).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.models import Donor, DonorType


FEATURE_NAMES: list[str] = [
    "donations_till_date",
    "avg_cycle_days",
    "is_regular",
    "is_one_time",
    "has_blood_group",
    "donated_earlier",
    "log_total_donations",
]


@dataclass
class SurvivalFeatures:
    """Survival model input row."""

    donations_till_date: int
    avg_cycle_days: int
    is_regular: int
    is_one_time: int
    has_blood_group: int
    donated_earlier: int
    log_total_donations: float

    def as_dict(self) -> dict:
        return {
            "donations_till_date": float(self.donations_till_date),
            "avg_cycle_days": float(self.avg_cycle_days),
            "is_regular": float(self.is_regular),
            "is_one_time": float(self.is_one_time),
            "has_blood_group": float(self.has_blood_group),
            "donated_earlier": float(self.donated_earlier),
            "log_total_donations": self.log_total_donations,
        }


def extract_survival_features(donor: Donor) -> SurvivalFeatures:
    """Build the survival feature row for one donor."""
    import math

    donations = int(donor.total_donations or 0)
    return SurvivalFeatures(
        donations_till_date=donations,
        avg_cycle_days=int(donor.avg_cycle_days or 0),
        is_regular=int(donor.donor_type == DonorType.REGULAR),
        is_one_time=int(donor.donor_type == DonorType.ONE_TIME),
        has_blood_group=int(
            donor.blood_group is not None
            and getattr(donor.blood_group, "value", str(donor.blood_group)) not in ("unknown", "")
        ),
        donated_earlier=int(bool(donor.donated_earlier)),
        log_total_donations=math.log1p(donations),
    )


def compute_duration_event(donor: Donor, today: date | None = None) -> tuple[int, int] | None:
    """Compute (duration_in_days, event_flag) for survival training.

    Returns None if the donor has no usable temporal anchor.
        event = 1 if Inactive (event observed)
        event = 0 if Active (right-censored — still "surviving")
    """
    if today is None:
        today = date.today()

    # Anchor: prefer last_donation_date; else registration date
    anchor = donor.last_donation_date
    if anchor is None:
        if donor.registered_at is None:
            return None
        anchor = (
            donor.registered_at.date()
            if isinstance(donor.registered_at, datetime)
            else donor.registered_at
        )

    is_inactive = not bool(donor.is_active)
    duration = max(1, (today - anchor).days)
    return duration, int(is_inactive)
