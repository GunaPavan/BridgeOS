"""Mock eRaktKosh client.

eRaktKosh is India's national Blood Bank Management System operated by MoHFW
via CDAC. The real platform exposes blood-bank directories, donor-camp
schedules, and (partial) real-time stock data across ~3,800 centres.

This module returns deterministic synthetic inventory data so the Bridge OS
demo can show "we plug into national infrastructure" without depending on
the live API (which has no public REST contract for inventory writes and
limited read access without partnership).

To swap for the real source: replace `fetch_inventory` with HTTP calls to
the appropriate eRaktKosh endpoint and map the response into `BloodBankStock`.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

# Curated set of real blood banks, calibrated to our patient-city distribution.
_BLOOD_BANKS = [
    ("Apollo Blood Bank", "Hyderabad", "Telangana", 17.388, 78.490, "+91-40-23607777"),
    ("CARE Hospital Blood Centre", "Hyderabad", "Telangana", 17.412, 78.450, "+91-40-30418888"),
    ("Yashoda Hospital Blood Bank", "Hyderabad", "Telangana", 17.426, 78.450, "+91-40-45674567"),
    ("Manipal Hospital Blood Bank", "Bangalore", "Karnataka", 12.958, 77.595, "+91-80-22221111"),
    ("Apollo Speciality Blood Centre", "Chennai", "Tamil Nadu", 13.063, 80.244, "+91-44-28293333"),
    ("AIIMS Blood Centre", "Delhi", "Delhi", 28.567, 77.210, "+91-11-26594444"),
    ("Tata Memorial Blood Bank", "Mumbai", "Maharashtra", 19.001, 72.843, "+91-22-24177000"),
    ("AIIMS Bhubaneswar Blood Bank", "Bhubaneswar", "Odisha", 20.296, 85.819, "+91-674-2476789"),
    ("PGIMER Blood Centre", "Chandigarh", "Chandigarh", 30.764, 76.776, "+91-172-2750000"),
    ("Sankalp Blood Centre", "Bangalore", "Karnataka", 12.972, 77.594, "+91-80-23456789"),
]

BLOOD_GROUPS = ("O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-")


@dataclass(frozen=True)
class BloodBankStock:
    name: str
    city: str
    state: str
    lat: float
    lng: float
    phone: str
    inventory: dict[str, int]
    last_updated: datetime


def _deterministic_inventory(seed_key: str) -> dict[str, int]:
    """Stable, plausible inventory derived from a hash of the bank name + day."""
    h = int(hashlib.md5(seed_key.encode("utf-8")).hexdigest(), 16)
    rng = random.Random(h)
    return {
        bg: rng.randint(0, 6) if bg.endswith("-") else rng.randint(3, 30)
        for bg in BLOOD_GROUPS
    }


def fetch_inventory(
    city: str | None = None,
    blood_group: str | None = None,
) -> list[BloodBankStock]:
    """Return a list of blood banks with their current stock, optionally
    filtered by city and/or to centres that have units of `blood_group`."""
    now = datetime.now(timezone.utc)
    bucket_day = now.strftime("%Y-%m-%d")

    out: list[BloodBankStock] = []
    for name, c, state, lat, lng, phone in _BLOOD_BANKS:
        if city and c.lower() != city.lower():
            continue
        seed_key = f"{name}::{bucket_day}"
        inv = _deterministic_inventory(seed_key)
        if blood_group and inv.get(blood_group, 0) == 0:
            continue
        out.append(
            BloodBankStock(
                name=name,
                city=c,
                state=state,
                lat=lat,
                lng=lng,
                phone=phone,
                inventory=inv,
                last_updated=now - timedelta(minutes=int(seed_key.__hash__() % 90)),
            )
        )
    return out


def sample_count() -> int:
    return len(_BLOOD_BANKS)
