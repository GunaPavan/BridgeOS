"""Expanded feature extraction — uses every signal in the dataset.

Builds the SAME features for both churn and survival models, so the bake-off
is apples-to-apples.

Features extracted from the existing 31 dataset columns:
    Numeric:
        donations_till_date
        avg_cycle_days
        days_since_last_contact
        days_since_registration
        latitude, longitude
        log_total_donations
    Binary:
        is_regular, is_one_time           (from donor_type)
        is_male, is_female                (from gender)
        has_blood_group, has_gender, donated_earlier
        on_bridge                         (whether bridge_id was populated)
        is_kell_negative                  (when we know — usually False)
    Categorical (one-hot):
        blood_group_one_hot               (8 ABO+Rh + Bombay + Unknown)
        registration_cohort               (year bucket: pre-2024 / 2024 / 2025 / 2026)
        geographic_cluster                (k-means k=8 on lat/lng)

NON-leaky: excludes total_calls, calls_to_donations_ratio, response_rate,
and days_since_last_donation (all derive from the rule that creates the labels).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

import numpy as np

from app.models import BloodGroup, Donor, DonorType, Gender


# These names MUST stay stable across train + predict
FEATURE_NAMES: list[str] = [
    # numeric
    "donations_till_date",
    "avg_cycle_days",
    "days_since_last_contact",
    "days_since_registration",
    "latitude",
    "longitude",
    "log_total_donations",
    # donor_type binary
    "is_regular",
    "is_one_time",
    # gender binary
    "is_male",
    "is_female",
    "has_gender",
    # data completeness
    "has_blood_group",
    "donated_earlier",
    "on_bridge",
    # blood group one-hot (9 — we collapse subtypes)
    "bg_A_pos",
    "bg_A_neg",
    "bg_B_pos",
    "bg_B_neg",
    "bg_AB_pos",
    "bg_AB_neg",
    "bg_O_pos",
    "bg_O_neg",
    "bg_bombay",
    # cohort buckets
    "cohort_pre_2024",
    "cohort_2024",
    "cohort_2025",
    "cohort_2026",
    # geographic clusters (k=8) — assigned at training time, frozen at predict time
    "geo_cluster_0",
    "geo_cluster_1",
    "geo_cluster_2",
    "geo_cluster_3",
    "geo_cluster_4",
    "geo_cluster_5",
    "geo_cluster_6",
    "geo_cluster_7",
]


SENTINEL_NEVER = 9999


@dataclass
class Features:
    values: dict[str, float]

    def as_vector(self) -> list[float]:
        return [self.values.get(name, 0.0) for name in FEATURE_NAMES]


def _days_since(d, today: date) -> int:
    if d is None:
        return SENTINEL_NEVER
    if isinstance(d, datetime):
        d = d.date()
    return max(0, (today - d).days)


def _cohort_bucket(reg_date) -> tuple[int, int, int, int]:
    """Return (pre_2024, 2024, 2025, 2026) one-hot.

    Donors registered after 2026 land in the 2026 bucket (newest cohort
    signal). Missing values default to pre_2024 (most-likely-churned prior).
    """
    if reg_date is None:
        return (1, 0, 0, 0)  # default to oldest cohort (most likely to have churned)
    if isinstance(reg_date, datetime):
        reg_date = reg_date.date()
    year = reg_date.year
    if year < 2024:
        return (1, 0, 0, 0)
    if year == 2024:
        return (0, 1, 0, 0)
    if year == 2025:
        return (0, 0, 1, 0)
    return (0, 0, 0, 1)  # 2026 and beyond


def _bg_one_hot(bg) -> dict[str, float]:
    """One-hot encode blood group across 9 categories."""
    val = getattr(bg, "value", str(bg)) if bg is not None else "unknown"
    mapping = {
        "A+": "bg_A_pos", "A-": "bg_A_neg",
        "B+": "bg_B_pos", "B-": "bg_B_neg",
        "AB+": "bg_AB_pos", "AB-": "bg_AB_neg",
        "O+": "bg_O_pos", "O-": "bg_O_neg",
        "Bombay": "bg_bombay",
    }
    out = {k: 0.0 for k in mapping.values()}
    if val in mapping:
        out[mapping[val]] = 1.0
    return out


def extract_features(
    donor: Donor,
    *,
    today: date | None = None,
    geo_cluster_id: int | None = None,
    on_bridge: bool | None = None,
) -> Features:
    """Build the v2 feature row for one donor.

    Args:
        donor: ORM row
        today: anchor date for time-since calculations
        geo_cluster_id: pre-computed k-means cluster (0..7); pass None to
            mark as missing (cluster 0 fallback)
        on_bridge: whether the donor has at least one bridge membership;
            inferred from donor.memberships if not provided
    """
    if today is None:
        today = date.today()

    if on_bridge is None:
        try:
            on_bridge = bool(donor.memberships)
        except Exception:
            on_bridge = False

    donations = int(donor.total_donations or 0)
    gender = donor.gender
    cohort = _cohort_bucket(donor.registered_at)

    vals: dict[str, float] = {
        "donations_till_date": float(donations),
        "avg_cycle_days": float(donor.avg_cycle_days or 0),
        "days_since_last_contact": float(_days_since(donor.last_contacted_date, today)),
        "days_since_registration": float(_days_since(donor.registered_at, today)),
        "latitude": float(donor.lat or 0.0),
        "longitude": float(donor.lng or 0.0),
        "log_total_donations": math.log1p(donations),

        "is_regular": float(donor.donor_type == DonorType.REGULAR),
        "is_one_time": float(donor.donor_type == DonorType.ONE_TIME),

        "is_male": float(gender == Gender.MALE),
        "is_female": float(gender == Gender.FEMALE),
        "has_gender": float(gender is not None),

        "has_blood_group": float(
            donor.blood_group is not None
            and getattr(donor.blood_group, "value", str(donor.blood_group)) not in ("unknown", "")
        ),
        "donated_earlier": float(bool(donor.donated_earlier)),
        "on_bridge": float(bool(on_bridge)),

        "cohort_pre_2024": float(cohort[0]),
        "cohort_2024": float(cohort[1]),
        "cohort_2025": float(cohort[2]),
        "cohort_2026": float(cohort[3]),
    }
    vals.update(_bg_one_hot(donor.blood_group))

    # Geographic cluster one-hot (8 clusters)
    for i in range(8):
        vals[f"geo_cluster_{i}"] = 0.0
    if geo_cluster_id is not None and 0 <= geo_cluster_id < 8:
        vals[f"geo_cluster_{geo_cluster_id}"] = 1.0

    return Features(values=vals)


# Geographic clustering — fit once at training, reused at predict time
class GeographicClusterer:
    """k-means clustering on (lat, lng) for k=8 regions."""

    def __init__(self, k: int = 8, seed: int = 42):
        self.k = k
        self.seed = seed
        self.kmeans = None

    def fit(self, lat_lng: np.ndarray) -> "GeographicClusterer":
        from sklearn.cluster import KMeans
        # Filter out (0,0) sentinel rows (missing geography)
        mask = ~((lat_lng[:, 0] == 0) & (lat_lng[:, 1] == 0))
        if mask.sum() < self.k:
            return self  # too few points to cluster
        self.kmeans = KMeans(
            n_clusters=self.k, random_state=self.seed, n_init=10
        ).fit(lat_lng[mask])
        return self

    def predict(self, lat_lng: np.ndarray) -> np.ndarray:
        if self.kmeans is None:
            return np.zeros(len(lat_lng), dtype=int)
        out = np.zeros(len(lat_lng), dtype=int)
        mask = ~((lat_lng[:, 0] == 0) & (lat_lng[:, 1] == 0))
        if mask.sum() > 0:
            out[mask] = self.kmeans.predict(lat_lng[mask])
        return out


def build_feature_matrix(
    donors: list[Donor],
    *,
    today: date | None = None,
    fit_geo: bool = True,
    geo_clusterer: GeographicClusterer | None = None,
    membership_lookup: dict | None = None,
) -> tuple[np.ndarray, GeographicClusterer]:
    """Build (n_donors x n_features) matrix for a donor list.

    Args:
        donors: list of Donor ORM rows
        today: anchor date
        fit_geo: if True, fit a new k-means on the geography; if False, requires
            geo_clusterer to be passed in
        geo_clusterer: pre-fitted clusterer (used at predict time)
        membership_lookup: optional dict[donor_id, bool] indicating whether
            each donor has at least one bridge membership

    Returns:
        (X, geo_clusterer) — the matrix and the fitted clusterer (for reuse)
    """
    if today is None:
        today = date.today()

    lat_lng = np.array([[d.lat or 0.0, d.lng or 0.0] for d in donors], dtype=np.float32)
    if fit_geo or geo_clusterer is None:
        geo_clusterer = GeographicClusterer().fit(lat_lng)
    cluster_ids = geo_clusterer.predict(lat_lng)

    rows = []
    for d, cid in zip(donors, cluster_ids):
        on_bridge = None
        if membership_lookup is not None:
            on_bridge = membership_lookup.get(d.id, False)
        feats = extract_features(d, today=today, geo_cluster_id=int(cid), on_bridge=on_bridge)
        rows.append(feats.as_vector())
    return np.array(rows, dtype=np.float32), geo_clusterer
