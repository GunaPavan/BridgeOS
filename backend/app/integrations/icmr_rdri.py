"""Mock ICMR Rare Donor Registry client.

The ICMR National Institute of Immunohaematology runs a Rare Donor Registry
(RDRI) for donors with rare blood phenotypes (Bombay, Rh-null, Kell-,
Lutheran-, McLeod, etc.) — critical for repeat-transfused thalassemia
patients at risk of alloimmunisation.

This module returns deterministic synthetic data so Bridge OS can surface
"verified by ICMR RDRI" badges without depending on the (currently
non-public) RDRI API. Real integration would replace `lookup_donors` with
authenticated HTTP calls and map back into `RegisteredRareDonor`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

_RARE_DONORS = [
    # (registry_id, initials, blood_group, kell_negative, phenotype, city, registered_year)
    ("RDRI-2022-HYD-014", "P.S.", "B+",  True,  "Kell-, Duffy(a+b+), Kidd(a+b-)", "Hyderabad",   2022),
    ("RDRI-2023-HYD-061", "M.D.", "B+",  True,  "Kell-, S+s+, Jka+Jkb+",          "Hyderabad",   2023),
    ("RDRI-2021-HYD-008", "U.V.", "B+",  True,  "Kell-, Duffy(a-b+)",             "Hyderabad",   2021),
    ("RDRI-2023-HYD-099", "E.A.", "O+",  True,  "Kell-",                          "Hyderabad",   2023),
    ("RDRI-2024-BLR-012", "A.N.", "O+",  True,  "Kell-, Diego(a-b+)",             "Bangalore",   2024),
    ("RDRI-2019-MUM-003", "R.M.", "AB-", False, "Bombay phenotype (rare hh)",     "Mumbai",      2019),
    ("RDRI-2024-CHE-031", "K.T.", "O+",  True,  "Kell-, Lutheran(a-b+)",          "Chennai",     2024),
    ("RDRI-2022-DEL-049", "S.M.", "B+",  False, "Rh-null variant (very rare)",    "Delhi",       2022),
]


@dataclass(frozen=True)
class RegisteredRareDonor:
    registry_id: str
    name_initials: str
    blood_group: str
    kell_negative: bool
    extended_phenotype: str
    city: str
    registered_year: int


def lookup_donors(
    blood_group: str | None = None,
    kell_negative: bool | None = None,
    city: str | None = None,
) -> list[RegisteredRareDonor]:
    """Return rare-phenotype donors matching the given filters."""
    out: list[RegisteredRareDonor] = []
    for (rid, initials, bg, kell, pheno, c, yr) in _RARE_DONORS:
        if blood_group and bg != blood_group:
            continue
        if kell_negative is not None and kell != kell_negative:
            continue
        if city and c.lower() != city.lower():
            continue
        out.append(
            RegisteredRareDonor(
                registry_id=rid,
                name_initials=initials,
                blood_group=bg,
                kell_negative=kell,
                extended_phenotype=pheno,
                city=c,
                registered_year=yr,
            )
        )
    return out


def last_sync() -> datetime:
    """Mock last-sync timestamp (now)."""
    return datetime.now(timezone.utc)


def sample_count() -> int:
    return len(_RARE_DONORS)
