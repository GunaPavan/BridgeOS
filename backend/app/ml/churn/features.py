"""Feature extraction for the multi-class churn model.

All features come straight from the Blood Warriors dataset — no synthetic
proxies. The features mirror what's in the donor's ORM row, derived where
needed (e.g. days_since_last_donation).

Feature contract (must stay stable across train+predict):
    response_rate            (proxy: 1/(1+0.3*calls_to_donations_ratio))
    calls_to_donations_ratio (raw)
    total_calls              (raw)
    donations_till_date      (raw — donor.total_donations)
    avg_cycle_days           (raw — donor.avg_cycle_days; 0 if null)
    days_since_last_donation (days from donor.last_donation_date to today)
    days_since_last_contact  (days from donor.last_contacted_date to today)
    days_since_registration  (days from donor.registered_at to today)
    is_regular               (1 if donor_type == REGULAR else 0)
    is_one_time              (1 if donor_type == ONE_TIME else 0)
    has_blood_group          (1 if blood_group is known else 0)
    donated_earlier          (raw bool)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.models import Donor, DonorType


# Feature set carefully chosen to AVOID label leakage.
#
# The Blood Warriors labels are rule-derived:
#   "Not donated 1Y"          := days_since_last_donation > 365
#   "Limited despite calls"   := total_calls > N AND donations_till_date low
# Including those fields as features lets the model memorize the rule (we
# observed AUC 1.000 with them — a clear leak). We drop them here.
#
# What remains are donor-characteristic features that capture engagement
# pattern WITHOUT defining the label rule directly.
FEATURE_NAMES: list[str] = [
    "donations_till_date",      # donation count (count, not threshold)
    "avg_cycle_days",           # rhythm — not used in labeling rule
    "days_since_last_contact",  # outreach recency — different from total_calls
    "days_since_registration",  # tenure — cohort effect
    "is_regular",               # declared donor_type
    "is_one_time",
    "has_blood_group",          # engagement proxy (Guests often skip)
    "donated_earlier",
]


@dataclass
class ChurnFeatures:
    """One donor's feature row for the multi-class churn model.

    Excludes the rule-defining features (total_calls, calls_to_donations_ratio,
    response_rate, days_since_last_donation) to avoid label leakage.
    """

    donations_till_date: int
    avg_cycle_days: int
    days_since_last_contact: int
    days_since_registration: int
    is_regular: int
    is_one_time: int
    has_blood_group: int
    donated_earlier: int

    def as_list(self) -> list[float]:
        """Return values in FEATURE_NAMES order — model input vector."""
        return [
            float(self.donations_till_date),
            float(self.avg_cycle_days),
            float(self.days_since_last_contact),
            float(self.days_since_registration),
            float(self.is_regular),
            float(self.is_one_time),
            float(self.has_blood_group),
            float(self.donated_earlier),
        ]


SENTINEL_NEVER_HAPPENED = 9999  # used when a date column is null (e.g. donor never contacted)


def extract_donor_features(donor: Donor, today: date | None = None) -> ChurnFeatures:
    """Build the feature row for one donor."""
    if today is None:
        today = date.today()

    def _days_since(d):
        if d is None:
            return SENTINEL_NEVER_HAPPENED
        if isinstance(d, datetime):
            d = d.date()
        return max(0, (today - d).days)

    return ChurnFeatures(
        donations_till_date=int(donor.total_donations or 0),
        avg_cycle_days=int(donor.avg_cycle_days or 0),
        days_since_last_contact=_days_since(donor.last_contacted_date),
        days_since_registration=_days_since(donor.registered_at),
        is_regular=int(donor.donor_type == DonorType.REGULAR),
        is_one_time=int(donor.donor_type == DonorType.ONE_TIME),
        has_blood_group=int(
            donor.blood_group is not None
            and getattr(donor.blood_group, "value", str(donor.blood_group)) not in ("unknown", "")
        ),
        donated_earlier=int(bool(donor.donated_earlier)),
    )
