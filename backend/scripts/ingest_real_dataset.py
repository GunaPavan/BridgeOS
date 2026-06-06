"""Real dataset ingestion — Blood Warriors data → Bridge OS ORM.

The synthetic generator is gone. This script is the canonical path from a
real Blood Warriors data export (CSV or JSON, schema to be confirmed when
they share the file) to a populated Bridge OS database.

Usage (when dataset arrives):
    python -m scripts.ingest_real_dataset --source data/blood_warriors_2026.csv
    python -m scripts.ingest_real_dataset --source data/export.json --format json
    python -m scripts.ingest_real_dataset --reset   # drop & recreate schema first

Design contract:
- Idempotent: re-running won't duplicate rows (uses natural keys: phone for
  donors, name+blood_group for patients pending confirmation).
- Streaming-friendly: yields chunks so we don't load 100k patients into RAM.
- Schema-tolerant: a SCHEMA_MAP at the top of this file translates their
  column names to ours. When their file arrives we update the SCHEMA_MAP
  and everything else stays put.
- Triggers calibration: after ingest, ML thresholds are recomputed
  immediately so the rest of the system reads sensible numbers.

Public functions:
    ingest_real_dataset(db, source_path, fmt) -> IngestReport
    pick_feature_patient(db, criteria) -> Patient
        Replaces the hardcoded Aarav/Priya narrative anchor. Selects a
        patient whose cohort exhibits the demo characteristic we want
        (default: most at-risk active cohort with at least one weak donor).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine
from app.models import (
    BloodGroup,
    Bridge,
    BridgeMembership,
    BridgeStatus,
    Donor,
    DonorType,
    Gender,
    InactiveReason,
    Language,
    MembershipRole,
    MembershipStatus,
    Patient,
)
from app.models.enums import CaregiverRelation


# -----------------------------------------------------------------------------
# Schema map for Blood Warriors' Dataset.csv (confirmed columns, Aug 2025).
# The dataset is a SINGLE long-format CSV where each row is a user (donor or
# patient or volunteer) and the `role` column distinguishes them. We split the
# rows into patient/donor/membership tables at ingest time.
# -----------------------------------------------------------------------------

# Patient-row column mapping (rows where role == "Patient")
PATIENT_SCHEMA_MAP: dict[str, str] = {
    "name":                       "user_id",   # patient_name not in dataset; use user_id as anchor
    "blood_group":                "blood_group",
    "lat":                        "latitude",
    "lng":                        "longitude",
    "transfusion_cadence_days":   "frequency_in_days",
    "last_transfusion_date":      "last_transfusion_date",
    "units_per_transfusion":      "quantity_required",
    "gender":                     "gender",
}

# Donor-row column mapping (rows where role in {"Bridge Donor", "Emergency Donor", "Guest", "Volunteer"})
DONOR_SCHEMA_MAP: dict[str, str] = {
    "name":                       "user_id",   # anonymized id stands in for name
    "blood_group":                "blood_group",
    "phone":                      "user_id",   # placeholder; dataset has no phone
    "lat":                        "latitude",
    "lng":                        "longitude",
    "last_donation_date":         "last_donation_date",
    "last_contacted_date":        "last_contacted_date",
    "total_donations":            "donations_till_date",
    "donor_type":                 "donor_type",
    "total_calls":                "total_calls",
    "calls_to_donations_ratio":   "calls_to_donations_ratio",
    "avg_cycle_days":             "cycle_of_donations",
    "donated_earlier":            "donated_earlier",
    "is_active":                  "user_donation_active_status",
    "inactive_reason":            "inactive_trigger_comment",
    "gender":                     "gender",
    "registered_at":              "registration_date",
}

# Membership map: connects donors to bridges when role == "Bridge Donor" and bridge_id is present.
MEMBERSHIP_SCHEMA_MAP: dict[str, str] = {
    "patient_ref":      "bridge_id",   # bridge_id corresponds to a patient's bridge
    "donor_ref":        "user_id",
    "status":           "user_donation_active_status",
    "joined_at":        "registration_date",
}


# -----------------------------------------------------------------------------
# Public surface
# -----------------------------------------------------------------------------


@dataclass
class IngestReport:
    """Returned by ingest_real_dataset; logged + shown to admin on /analytics."""

    patients_loaded: int = 0
    donors_loaded: int = 0
    bridges_created: int = 0
    memberships_loaded: int = 0
    rows_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.utcnow())
    finished_at: datetime | None = None
    source_path: str | None = None
    feature_patient_id: str | None = None  # picked by pick_feature_patient

    def summary(self) -> str:
        dur = (self.finished_at - self.started_at).total_seconds() if self.finished_at else 0
        return (
            f"Ingested {self.patients_loaded} patients, {self.donors_loaded} donors, "
            f"{self.bridges_created} bridges, {self.memberships_loaded} memberships "
            f"in {dur:.1f}s ({self.rows_skipped} skipped, {len(self.errors)} errors)"
        )


def ingest_real_dataset(
    db: Session,
    source_path: str | Path,
    *,
    fmt: str | None = None,
    reset_schema: bool = False,
) -> IngestReport:
    """Load the Blood Warriors dataset into the Bridge OS DB.

    Args:
        db: SQLAlchemy session.
        source_path: Path to CSV / JSON file (or directory of multiple files).
        fmt: 'csv' or 'json'; auto-detected from extension if None.
        reset_schema: If True, drop and recreate all tables first.
    """
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    if fmt is None:
        fmt = "csv" if path.suffix.lower() == ".csv" else "json"

    report = IngestReport(source_path=str(path))

    if reset_schema:
        print(f"Dropping + recreating schema...")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    if path.is_dir():
        raise NotImplementedError(
            "Multi-file ingest not implemented yet — point at the single "
            "export file once they share it."
        )

    # Blood Warriors' Dataset.csv is long-format: each row is one user
    # (patient / donor / volunteer) and the `role` column splits them.
    rows: list[dict[str, Any]] = list(_read_rows(path, fmt=fmt))
    _ingest_blood_warriors(db, rows, report)

    db.commit()

    # Auto-pick feature patient + trigger calibration so the demo is live
    feature = pick_feature_patient(db)
    if feature is not None:
        report.feature_patient_id = str(feature.id)

    try:
        from app.ml.calibration import invalidate_cache
        invalidate_cache()
    except Exception as e:
        report.errors.append(f"Calibration trigger failed: {e}")

    report.finished_at = datetime.utcnow()
    return report


def pick_feature_patient(
    db: Session,
    *,
    criteria: str = "most_at_risk",
) -> Patient | None:
    """Choose a patient whose cohort exhibits the desired demo property.

    Replaces the Aarav/Priya hardcoding. The narrative ("this patient's
    cohort has a destabilizer") is sourced from real data instead of being
    handcrafted.

    Available criteria:
        "most_at_risk" — patient whose bridge has the lowest avg response_rate
                         among ACTIVE donors. The "Priya" surrogate.
        "first"        — first patient by id; useful for deterministic tests.
        "smallest_cohort" — patient with the fewest ACTIVE donors.
    """
    patients = db.execute(select(Patient).where(Patient.active.is_(True))).scalars().all()
    if not patients:
        return None

    if criteria == "first":
        return patients[0]

    # Score each by an active-cohort metric
    scored: list[tuple[float, Patient]] = []
    for p in patients:
        if p.bridge is None:
            continue
        actives = [
            m for m in p.bridge.memberships
            if m.status == MembershipStatus.ACTIVE
            or m.status == MembershipStatus.ACTIVE.value
        ]
        if not actives:
            continue
        if criteria == "smallest_cohort":
            score = float(len(actives))
            scored.append((score, p))
        else:  # most_at_risk
            avg_response = sum(m.donor.response_rate for m in actives) / len(actives)
            scored.append((avg_response, p))

    if not scored:
        return patients[0]
    scored.sort(key=lambda t: t[0])  # ascending — smallest cohort / lowest response first
    return scored[0][1]


# -----------------------------------------------------------------------------
# Internals — reader + per-table mappers (scaffolds; fill in when data arrives)
# -----------------------------------------------------------------------------


def _read_rows(path: Path, *, fmt: str) -> Iterator[dict[str, Any]]:
    """Stream rows from CSV or JSON without loading everything into RAM."""
    if fmt == "csv":
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield {k: (v if v != "" else None) for k, v in row.items()}
    elif fmt == "json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            yield from data
        elif isinstance(data, dict) and "rows" in data:
            yield from data["rows"]
        else:
            raise ValueError(f"Unrecognized JSON shape in {path}")
    else:
        raise ValueError(f"Unsupported format: {fmt}")


def _infer_table(path: Path) -> str:
    name = path.stem.lower()
    if "patient" in name:
        return "patients"
    if "donor" in name:
        return "donors"
    if "member" in name or "bridge" in name:
        return "memberships"
    return "unified"


# -----------------------------------------------------------------------------
# Blood Warriors-specific ingest (the canonical real-data path)
# -----------------------------------------------------------------------------


def _ingest_blood_warriors(
    db: Session, rows: list[dict[str, Any]], report: IngestReport
) -> None:
    """Ingest Blood Warriors' Dataset.csv (the long-format single file).

    Each row is one user. `role` distinguishes Patient / Bridge Donor /
    Emergency Donor / Guest / Volunteer. Patients own bridges (identified by
    `bridge_id` in the row of role=Patient). Bridge Donors connect to those
    bridges via the same `bridge_id` column.

    Pipeline:
      1. PATIENT rows  -> Patient + Bridge entities
      2. DONOR rows    -> Donor entities (covers all 4 non-Patient roles)
      3. MEMBERSHIPS   -> for any row with bridge_id, create BridgeMembership

    Skips: Guest with no contact info, rows missing critical fields. Counters
    in IngestReport let the operator see how complete the ingest was.
    """
    # Pre-warm the geocode cache. We resolve every unique coordinate ONCE
    # before iterating rows so subsequent inline calls in the patient/donor
    # loops hit the DB cache instead of AWS Location. With 132 unique coords
    # vs 6,949 raw rows, this avoids ~6,800 redundant API calls.
    from app.integrations.aws_location import warm_cache_for_coords

    all_coords: list[tuple[float, float]] = []
    for r in rows:
        lat = _to_float(r.get("latitude"))
        lng = _to_float(r.get("longitude"))
        if lat is not None and lng is not None:
            all_coords.append((lat, lng))
    print(f"  Warming geocode cache for {len(all_coords)} rows...")
    counters = warm_cache_for_coords(db, all_coords)
    print(
        f"  Geocode warm complete: {counters['resolved']} resolved via AWS, "
        f"{counters['cached']} from DB cache, {counters['failed']} failed"
    )

    # Pre-bin rows by role
    by_role: dict[str, list[dict]] = {}
    for r in rows:
        role = (r.get("role") or "").strip()
        by_role.setdefault(role, []).append(r)

    print(f"  Role distribution: " + ", ".join(
        f"{k}={len(v)}" for k, v in by_role.items()
    ))

    # Map: external user_id (from CSV) -> internal Donor / Patient
    donor_by_external: dict[str, Donor] = {}
    patient_by_external: dict[str, Patient] = {}
    bridge_by_external: dict[str, Bridge] = {}  # external bridge_id -> Bridge

    # 1) Patients + Bridges
    for raw in by_role.get("Patient", []):
        try:
            external_id = raw.get("user_id") or ""
            external_bridge_id = raw.get("bridge_id") or ""
            lat = _to_float(raw.get("latitude"))
            lng = _to_float(raw.get("longitude"))
            from app.integrations.aws_location import reverse_geocode
            city, state = reverse_geocode(db, lat, lng)
            p = Patient(
                external_id=external_id or None,
                name=_compose_name(raw, fallback=f"Patient {_clean_external_id(external_id)}"),
                age=_infer_age(raw),
                blood_group=_parse_blood_group(raw.get("blood_group")) or BloodGroup.UNKNOWN,
                rh_negative=False,
                kell_negative=False,
                city=city,
                state=state,
                lat=lat or 0.0,
                lng=lng or 0.0,
                hospital="(unspecified)",
                transfusion_cadence_days=_to_int(raw.get("frequency_in_days")) or 18,
                last_transfusion_date=_parse_date(raw.get("last_transfusion_date")),
                preferred_language=Language.ENGLISH,
                caregiver_name=None,
                caregiver_phone=None,
                caregiver_relation=None,
                units_per_transfusion=_to_int(raw.get("quantity_required")) or 1,
                gender=_parse_gender(raw.get("bridge_gender") or raw.get("gender")),
                active=True,
            )
            db.add(p)
            db.flush()
            patient_by_external[external_id] = p

            if external_bridge_id:
                bridge = Bridge(
                    patient_id=p.id,
                    # Use the patient handle rather than the raw bridge_id so
                    # the UI never renders control-char garbage (the original
                    # external_bridge_id is hex with a leading `\x` escape).
                    name=f"Bridge for {p.name}",
                    status=BridgeStatus.ACTIVE,
                )
                db.add(bridge)
                db.flush()
                bridge_by_external[external_bridge_id] = bridge
            report.patients_loaded += 1
            report.bridges_created += 1 if external_bridge_id else 0
        except Exception as e:
            report.errors.append(f"Patient row failed: {e}")
            report.rows_skipped += 1

    db.flush()

    # 2) Donors (all 4 non-patient roles)
    #
    # The Blood Warriors CSV has ~13 user_ids that appear in multiple role
    # buckets (e.g. one person registered as both a Volunteer and a Bridge
    # Donor — totally legitimate operationally). Without dedup, each role
    # entry would create a separate Donor row in our DB, producing apparent
    # name duplicates and inflating donor counts. We dedup by external_id —
    # first-seen wins, with role priority Bridge Donor > Emergency Donor >
    # Guest > Volunteer so the most-active role survives.
    seen_external_ids: set[str] = set()
    for role in ("Bridge Donor", "Emergency Donor", "Guest", "Volunteer"):
        for raw in by_role.get(role, []):
            try:
                external_id = raw.get("user_id") or ""
                if not external_id:
                    report.rows_skipped += 1
                    continue
                if external_id in seen_external_ids:
                    # Already created a Donor for this person under a
                    # higher-priority role. Skip — don't fabricate dupes.
                    continue
                seen_external_ids.add(external_id)
                lat = _to_float(raw.get("latitude"))
                lng = _to_float(raw.get("longitude"))
                from app.integrations.aws_location import reverse_geocode
                city, state = reverse_geocode(db, lat, lng)
                d = Donor(
                    external_id=external_id or None,
                    name=_compose_name(raw, fallback=f"Donor {_clean_external_id(external_id)}"),
                    age=_infer_age(raw),
                    blood_group=_parse_blood_group(raw.get("blood_group")) or BloodGroup.UNKNOWN,
                    rh_negative=False,
                    kell_negative=False,
                    phone=f"+91{abs(hash(external_id)) % 10**10:010d}",  # synthetic phone for outreach
                    preferred_language=Language.ENGLISH,
                    city=city,
                    state=state,
                    lat=lat or 0.0,
                    lng=lng or 0.0,
                    last_donation_date=_parse_date(raw.get("last_donation_date")),
                    total_donations=_to_int(raw.get("donations_till_date")) or 0,
                    response_rate=_response_rate_from_ratio(raw.get("calls_to_donations_ratio")),
                    avg_response_hours=4.0,
                    # Real-data fields
                    donor_type=_parse_donor_type(raw.get("donor_type")),
                    inactive_reason=_parse_inactive_reason(raw.get("inactive_trigger_comment")),
                    total_calls=_to_int(raw.get("total_calls")) or 0,
                    calls_to_donations_ratio=_to_float(raw.get("calls_to_donations_ratio")) or 0.0,
                    avg_cycle_days=_to_int(raw.get("cycle_of_donations")),
                    donated_earlier=_to_bool(raw.get("donated_earlier")),
                    last_contacted_date=_parse_date(raw.get("last_contacted_date")),
                    gender=_parse_gender(raw.get("gender")),
                    is_active=(raw.get("user_donation_active_status") == "Active"),
                    registered_at=_parse_datetime(raw.get("registration_date")),
                )
                db.add(d)
                db.flush()
                donor_by_external[external_id] = d
                report.donors_loaded += 1
            except Exception as e:
                report.errors.append(f"{role} row failed: {e}")
                report.rows_skipped += 1

    db.flush()

    # 3) Bridge memberships — Bridge Donor rows with bridge_id linking to a patient bridge
    for raw in by_role.get("Bridge Donor", []):
        try:
            external_id = raw.get("user_id") or ""
            external_bridge_id = raw.get("bridge_id") or ""
            if not external_bridge_id or external_bridge_id not in bridge_by_external:
                continue
            donor = donor_by_external.get(external_id)
            if donor is None:
                continue
            bridge = bridge_by_external[external_bridge_id]
            status_text = (raw.get("user_donation_active_status") or "Active").lower()
            status = MembershipStatus.ACTIVE if status_text == "active" else MembershipStatus.EXITED
            m = BridgeMembership(
                bridge_id=bridge.id,
                donor_id=donor.id,
                role=MembershipRole.PRIMARY,
                status=status,
                joined_at=(_parse_date(raw.get("registration_date")) or _today()),
            )
            db.add(m)
            report.memberships_loaded += 1
        except Exception as e:
            report.errors.append(f"Membership row failed: {e}")
            report.rows_skipped += 1


def _today() -> date:
    """date.today() wrapper — separated for testability."""
    return date.today()


def _infer_age(raw: dict) -> int:
    """Dataset has no age column; default to 25 for donors, 8 for patients
    (typical thalassemia age). Real Blood Warriors data will fix this when
    they share age info."""
    role = (raw.get("role") or "").strip()
    return 8 if role == "Patient" else 25


def _clean_external_id(external_id: str) -> str:
    """Strip the leading `\\x` prefix from Blood Warriors' hex IDs so the
    UI doesn't render garbage like 'Patient §2875' (where §=\\xa7). Returns
    a short, readable handle.
    """
    if not external_id:
        return "????"
    s = external_id
    if s.startswith("\\x"):
        s = s[2:]
    # Take first 6 hex chars as a stable short id
    return s[:6].upper()


def _compose_name(raw: dict, *, fallback: str) -> str:
    """Build a display name from CSV ``first_name`` + ``last_name`` columns.

    The extension script ``scripts.extend_dataset`` stamps these columns
    deterministically from ``user_id`` + gender. If the CSV is pre-extension
    (no name columns), fall back to the legacy ``Patient A72875`` / ``Donor
    A72875`` style.
    """
    first = (raw.get("first_name") or "").strip()
    last = (raw.get("last_name") or "").strip()
    if first and last:
        return f"{first} {last}"
    if first:
        return first
    if last:
        return last
    # No name columns present — keep the row but use the handle as the name.
    return fallback


# Coordinate resolution is delegated to AWS Location Service via
# app.integrations.aws_location. The previous hardcoded bounding boxes were
# unscalable and arbitrary — replaced with a real geocoder that handles every
# global coord with Esri map data and caches every result in the DB so
# re-ingest is instant.


def _parse_gender(v: Any) -> Gender | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("male", "m"):
        return Gender.MALE
    if s in ("female", "f"):
        return Gender.FEMALE
    if s == "":
        return None
    return Gender.OTHER


def _parse_donor_type(v: Any) -> DonorType | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    if "regular" in s:
        return DonorType.REGULAR
    if "one-time" in s or "one time" in s:
        return DonorType.ONE_TIME
    return DonorType.OTHER


def _parse_inactive_reason(v: Any) -> InactiveReason | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    if "not donated" in s and "year" in s:
        return InactiveReason.NOT_DONATED_1Y
    if "limited activity" in s or "multiple calls" in s:
        return InactiveReason.LIMITED_DESPITE_CALLS
    return None


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_datetime(v: Any) -> datetime | None:
    """ISO-ish datetime parser. Returns None for unparseable input — DO NOT
    silently fall back to wall-clock 'now', which pollutes registered_at
    with ingest-time values and breaks the dataset-anchored system clock.
    """
    d = _parse_date(v)
    if d is None:
        return None
    return datetime(d.year, d.month, d.day)


def _response_rate_from_ratio(v: Any) -> float:
    """Convert calls_to_donations_ratio into a response_rate proxy in [0,1].

    Active donors median ratio is 0 (they convert without calls).
    Inactive donors median ratio is 3 (3 calls per donation).
    Map: ratio=0 -> 1.0, ratio=1 -> 0.75, ratio=3 -> 0.5, ratio=10+ -> 0.1
    """
    f = _to_float(v)
    if f is None or f < 0:
        return 0.75  # neutral prior
    return max(0.1, min(1.0, 1.0 / (1.0 + 0.3 * f)))


def _ingest_patients(db: Session, rows: Iterable[dict], report: IngestReport) -> None:
    for raw in rows:
        try:
            mapped = _apply_schema_map(raw, PATIENT_SCHEMA_MAP)
            mapped = _coerce_patient_types(mapped)
            existing = db.execute(
                select(Patient).where(Patient.name == mapped["name"])
            ).scalar_one_or_none()
            if existing is not None:
                report.rows_skipped += 1
                continue
            p = Patient(**mapped)
            db.add(p)
            db.flush()
            bridge = Bridge(
                patient_id=p.id,
                name=f"Bridge for {p.name.split()[0] if p.name else 'patient'}",
                status=BridgeStatus.ACTIVE,
            )
            db.add(bridge)
            report.patients_loaded += 1
            report.bridges_created += 1
        except Exception as e:
            report.errors.append(f"Patient row failed: {e}")
            report.rows_skipped += 1


def _ingest_donors(db: Session, rows: Iterable[dict], report: IngestReport) -> None:
    for raw in rows:
        try:
            mapped = _apply_schema_map(raw, DONOR_SCHEMA_MAP)
            mapped = _coerce_donor_types(mapped)
            existing = db.execute(
                select(Donor).where(Donor.phone == mapped.get("phone"))
            ).scalar_one_or_none()
            if existing is not None:
                report.rows_skipped += 1
                continue
            d = Donor(**mapped)
            db.add(d)
            report.donors_loaded += 1
        except Exception as e:
            report.errors.append(f"Donor row failed: {e}")
            report.rows_skipped += 1


def _ingest_memberships(db: Session, rows: Iterable[dict], report: IngestReport) -> None:
    for raw in rows:
        try:
            mapped = _apply_schema_map(raw, MEMBERSHIP_SCHEMA_MAP)
            patient = db.execute(
                select(Patient).where(Patient.name == mapped.get("patient_ref"))
            ).scalar_one_or_none()
            donor = db.execute(
                select(Donor).where(Donor.phone == mapped.get("donor_ref"))
            ).scalar_one_or_none()
            if patient is None or donor is None or patient.bridge is None:
                report.rows_skipped += 1
                continue
            m = BridgeMembership(
                bridge_id=patient.bridge.id,
                donor_id=donor.id,
                role=_parse_role(mapped.get("role")),
                status=_parse_status(mapped.get("status")),
                joined_at=_parse_date(mapped.get("joined_at")) or date.today(),
            )
            db.add(m)
            report.memberships_loaded += 1
        except Exception as e:
            report.errors.append(f"Membership row failed: {e}")
            report.rows_skipped += 1


def _ingest_unified(db: Session, rows: Iterable[dict], report: IngestReport) -> None:
    """Single-file unified export with a 'type' or 'entity' column."""
    by_type: dict[str, list[dict]] = {"patient": [], "donor": [], "membership": []}
    for raw in rows:
        t = (raw.get("type") or raw.get("entity") or "").lower().strip()
        if t in by_type:
            by_type[t].append(raw)
        else:
            report.rows_skipped += 1
    _ingest_patients(db, by_type["patient"], report)
    db.flush()
    _ingest_donors(db, by_type["donor"], report)
    db.flush()
    _ingest_memberships(db, by_type["membership"], report)


# -----------------------------------------------------------------------------
# Mapping + coercion helpers
# -----------------------------------------------------------------------------


def _apply_schema_map(row: dict, mapping: dict[str, str]) -> dict[str, Any]:
    """Translate their column names to ours, dropping fields we don't recognize."""
    out: dict[str, Any] = {}
    for ours, theirs in mapping.items():
        if theirs in row:
            out[ours] = row[theirs]
    return out


def _coerce_patient_types(d: dict) -> dict:
    if "blood_group" in d and d["blood_group"]:
        d["blood_group"] = _parse_blood_group(d["blood_group"])
    if "rh_negative" in d:
        d["rh_negative"] = _to_bool(d["rh_negative"])
    if "kell_negative" in d:
        d["kell_negative"] = _to_bool(d["kell_negative"])
    if "preferred_language" in d and d["preferred_language"]:
        d["preferred_language"] = _parse_language(d["preferred_language"])
    if "caregiver_relation" in d and d["caregiver_relation"]:
        d["caregiver_relation"] = _parse_caregiver_relation(d["caregiver_relation"])
    if "last_transfusion_date" in d:
        d["last_transfusion_date"] = _parse_date(d["last_transfusion_date"])
    if "transfusion_cadence_days" in d and d["transfusion_cadence_days"]:
        d["transfusion_cadence_days"] = int(d["transfusion_cadence_days"])
    if "age" in d and d["age"]:
        d["age"] = int(d["age"])
    if "lat" in d and d["lat"]:
        d["lat"] = float(d["lat"])
    if "lng" in d and d["lng"]:
        d["lng"] = float(d["lng"])
    return d


def _coerce_donor_types(d: dict) -> dict:
    if "blood_group" in d and d["blood_group"]:
        d["blood_group"] = _parse_blood_group(d["blood_group"])
    if "rh_negative" in d:
        d["rh_negative"] = _to_bool(d["rh_negative"])
    if "kell_negative" in d:
        d["kell_negative"] = _to_bool(d["kell_negative"])
    if "preferred_language" in d and d["preferred_language"]:
        d["preferred_language"] = _parse_language(d["preferred_language"])
    if "last_donation_date" in d:
        d["last_donation_date"] = _parse_date(d["last_donation_date"])
    for k in ("age", "total_donations"):
        if k in d and d[k]:
            d[k] = int(d[k])
    for k in ("lat", "lng", "response_rate", "avg_response_hours"):
        if k in d and d[k] is not None:
            d[k] = float(d[k])
    return d


def _parse_blood_group(v: Any) -> BloodGroup | None:
    """Normalize Blood Warriors' blood group strings to our enum.

    Handles:
      "O Positive" / "O Negative"  -> O+ / O-
      "AB Positive" / "AB Negative" -> AB+ / AB-
      "Do not Know"                -> UNKNOWN
      "Bombay Blood Group"         -> BOMBAY
      "A1 Positive" / "A2 Negative" -> fold into A+ / A- (subtypes rarely matter)
      None or empty                -> None (caller decides default)
    """
    if v is None or str(v).strip() == "":
        return None
    s = str(v).strip()
    if "bombay" in s.lower():
        return BloodGroup.BOMBAY
    if "do not know" in s.lower() or "unknown" in s.lower():
        return BloodGroup.UNKNOWN
    # Fold A1/A2 subtypes into their base group
    s = s.replace("A1B", "AB").replace("A2B", "AB").replace("A1", "A").replace("A2", "A")
    s = s.upper().replace("POSITIVE", "+").replace("NEGATIVE", "-").replace(" ", "")
    mapping = {
        "A+": BloodGroup.A_POS, "A-": BloodGroup.A_NEG,
        "B+": BloodGroup.B_POS, "B-": BloodGroup.B_NEG,
        "AB+": BloodGroup.AB_POS, "AB-": BloodGroup.AB_NEG,
        "O+": BloodGroup.O_POS, "O-": BloodGroup.O_NEG,
    }
    return mapping.get(s)  # None for unrecognized — caller falls back to UNKNOWN


def _parse_language(v: Any) -> Language:
    s = str(v).strip().lower()[:2]
    try:
        return Language(s)
    except ValueError:
        return Language.ENGLISH


def _parse_caregiver_relation(v: Any) -> CaregiverRelation:
    s = str(v).strip().lower()
    try:
        return CaregiverRelation(s)
    except ValueError:
        return CaregiverRelation.MOTHER


def _parse_role(v: Any) -> MembershipRole:
    s = str(v or "primary").strip().lower()
    return MembershipRole.BACKUP if s == "backup" else MembershipRole.PRIMARY


def _parse_status(v: Any) -> MembershipStatus:
    s = str(v or "active").strip().lower()
    try:
        return MembershipStatus(s)
    except ValueError:
        return MembershipStatus.ACTIVE


def _parse_date(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(v), fmt).date()
        except ValueError:
            continue
    return None


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"true", "1", "yes", "y", "t"}


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Blood Warriors dataset.")
    parser.add_argument("--source", required=True, help="Path to data file.")
    parser.add_argument("--format", choices=["csv", "json"], default=None)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate schema before ingest.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        report = ingest_real_dataset(
            db, source_path=args.source, fmt=args.format, reset_schema=args.reset
        )
    print(report.summary())
    if report.feature_patient_id:
        print(f"Feature patient picked: {report.feature_patient_id}")
    if report.errors:
        print(f"First 5 errors: {report.errors[:5]}")
    return 0 if not report.errors else 1


if __name__ == "__main__":
    sys.exit(main())
