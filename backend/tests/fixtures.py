"""Generic test fixture builder — replaces app.synthetic in test contexts.

The synthetic generator is being removed in favor of real Blood Warriors
data ingestion. But the test suite still needs to populate a DB with a
known shape so we can exercise API contracts, filter behavior, ML
predictions, and full E2E flows.

Design goals:
- DETERMINISTIC: same `seed` parameter -> identical rows. No randomness leaks.
- COMPLETE: every required ORM field populated with sensible defaults.
- GENERIC: NO real person names, NO Aarav/Priya narrative anchors. Patients
  named "Patient 1", "Patient 2", etc. Donors named "Donor 001", etc.
- SHAPEABLE: builders accept knobs so individual tests can construct the
  exact distribution they need (e.g. "give me 1 bridge with 1 destabilizer").

This file lives under tests/ so it's never imported by production code.

Public surface:
    build_test_dataset(db, n_patients, n_donors, seed) -> TestDataset
    build_minimal_bridge(db, n_donors, weak_donor_count, seed) -> Bridge
    build_feature_bridge(db, ...) -> Bridge with a known destabilizer
        (replaces the Aarav+Priya narrative in tests)
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Bridge,
    BridgeMembership,
    BridgeStatus,
    Donor,
    Language,
    MembershipRole,
    MembershipStatus,
    Patient,
)
from app.models.enums import CaregiverRelation


# Blood-group compatibility (donor -> recipient). Same table as production.
_COMPAT: dict[BloodGroup, set[BloodGroup]] = {
    BloodGroup.O_NEG: set(BloodGroup),
    BloodGroup.O_POS: {BloodGroup.O_POS, BloodGroup.A_POS, BloodGroup.B_POS, BloodGroup.AB_POS},
    BloodGroup.A_NEG: {BloodGroup.A_NEG, BloodGroup.A_POS, BloodGroup.AB_NEG, BloodGroup.AB_POS},
    BloodGroup.A_POS: {BloodGroup.A_POS, BloodGroup.AB_POS},
    BloodGroup.B_NEG: {BloodGroup.B_NEG, BloodGroup.B_POS, BloodGroup.AB_NEG, BloodGroup.AB_POS},
    BloodGroup.B_POS: {BloodGroup.B_POS, BloodGroup.AB_POS},
    BloodGroup.AB_NEG: {BloodGroup.AB_NEG, BloodGroup.AB_POS},
    BloodGroup.AB_POS: {BloodGroup.AB_POS},
}


def _can_donate(donor_bg: BloodGroup, recipient_bg: BloodGroup) -> bool:
    return recipient_bg in _COMPAT[donor_bg]


@dataclass
class TestDataset:
    """Container for a built dataset; analogous to synthetic.GeneratedData."""

    patients: list[Patient] = field(default_factory=list)
    donors: list[Donor] = field(default_factory=list)
    bridges: list[Bridge] = field(default_factory=list)
    memberships: list[BridgeMembership] = field(default_factory=list)
    feature_patient: Patient | None = None  # The narrative anchor for tests

    @property
    def feature_bridge(self) -> Bridge | None:
        if self.feature_patient is None:
            return None
        return self.feature_patient.bridge


# ----- Helpers -----------------------------------------------------------------


def _make_patient(idx: int, *, blood_group: BloodGroup, rng: random.Random) -> Patient:
    """Build a generic Patient with predictable attributes."""
    cities = [
        ("Hyderabad", "Telangana", 17.3850, 78.4867),
        ("Bengaluru", "Karnataka", 12.9716, 77.5946),
        ("Chennai", "Tamil Nadu", 13.0827, 80.2707),
        ("Mumbai", "Maharashtra", 19.0760, 72.8777),
        ("Delhi", "Delhi", 28.7041, 77.1025),
    ]
    city, state, lat, lng = cities[idx % len(cities)]
    return Patient(
        name=f"Patient {idx:03d}",
        age=rng.randint(3, 18),
        blood_group=blood_group,
        rh_negative=blood_group in {BloodGroup.O_NEG, BloodGroup.A_NEG, BloodGroup.B_NEG, BloodGroup.AB_NEG},
        kell_negative=rng.random() < 0.3,
        city=city,
        state=state,
        lat=lat,
        lng=lng,
        hospital=f"Hospital {(idx % 5) + 1}",
        transfusion_cadence_days=rng.choice([14, 18, 21, 28]),
        last_transfusion_date=date.today() - timedelta(days=rng.randint(1, 14)),
        preferred_language=rng.choice(list(Language)),
        caregiver_name=f"Caregiver of Patient {idx:03d}",
        caregiver_phone=f"+9199{idx:08d}",
        caregiver_relation=CaregiverRelation.MOTHER,
        active=True,
    )


def _make_donor(idx: int, *, blood_group: BloodGroup, rng: random.Random) -> Donor:
    """Build a generic Donor with predictable attributes."""
    cities = [
        ("Hyderabad", "Telangana", 17.3850, 78.4867),
        ("Bengaluru", "Karnataka", 12.9716, 77.5946),
        ("Chennai", "Tamil Nadu", 13.0827, 80.2707),
        ("Mumbai", "Maharashtra", 19.0760, 72.8777),
    ]
    city, state, lat, lng = cities[idx % len(cities)]
    return Donor(
        name=f"Donor {idx:03d}",
        age=rng.randint(20, 55),
        blood_group=blood_group,
        rh_negative=blood_group in {BloodGroup.O_NEG, BloodGroup.A_NEG, BloodGroup.B_NEG, BloodGroup.AB_NEG},
        kell_negative=rng.random() < 0.4,
        phone=f"+9198{idx:08d}",
        preferred_language=rng.choice(list(Language)),
        city=city,
        state=state,
        lat=lat,
        lng=lng,
        last_donation_date=date.today() - timedelta(days=rng.randint(30, 200)),
        total_donations=rng.randint(3, 20),
        response_rate=rng.uniform(0.55, 0.95),
        avg_response_hours=rng.uniform(2.0, 12.0),
        is_active=True,
    )


# ----- Public builders ---------------------------------------------------------


def build_test_dataset(
    db: Session,
    *,
    n_patients: int = 10,
    n_donors: int = 100,
    n_donors_per_bridge: int = 8,
    feature_destabilizer: bool = True,
    seed: int = 42,
) -> TestDataset:
    """Build a complete dataset directly in the DB. Drop-in replacement for
    ``generate(session, SyntheticConfig(num_patients=N, num_donors=M))``.

    Returns a ``TestDataset`` whose ``feature_patient`` is patient 0 — the
    designated narrative anchor for tests that previously pinned on Aarav.

    If ``feature_destabilizer=True``, the feature bridge will contain ONE
    donor with a very low response rate (the generic equivalent of the
    Priya destabilizer). Tests that previously asserted on Priya should
    instead use ``feature_bridge_destabilizer(bridge)`` (below).
    """
    rng = random.Random(seed)
    out = TestDataset()

    # Donors first so we can route them by compatibility
    bg_distribution = [
        (BloodGroup.O_POS, 0.36),
        (BloodGroup.B_POS, 0.32),
        (BloodGroup.A_POS, 0.21),
        (BloodGroup.AB_POS, 0.07),
        (BloodGroup.O_NEG, 0.02),
        (BloodGroup.B_NEG, 0.01),
        (BloodGroup.A_NEG, 0.005),
        (BloodGroup.AB_NEG, 0.005),
    ]

    def _draw_bg() -> BloodGroup:
        r = rng.random()
        cum = 0.0
        for bg, w in bg_distribution:
            cum += w
            if r < cum:
                return bg
        return BloodGroup.O_POS

    for i in range(n_donors):
        d = _make_donor(i, blood_group=_draw_bg(), rng=rng)
        db.add(d)
        out.donors.append(d)

    for i in range(n_patients):
        bg = _draw_bg()
        p = _make_patient(i, blood_group=bg, rng=rng)
        db.add(p)
        out.patients.append(p)

    db.flush()  # populate IDs

    # First patient is the feature anchor
    feature = out.patients[0]
    out.feature_patient = feature

    # Build bridges + memberships
    for idx, patient in enumerate(out.patients):
        bridge = Bridge(
            patient_id=patient.id,
            name=f"Bridge {idx:03d}",
            status=BridgeStatus.ACTIVE,
        )
        db.add(bridge)
        out.bridges.append(bridge)
        db.flush()

        compatible = [d for d in out.donors if _can_donate(d.blood_group, patient.blood_group)]
        if patient.kell_negative:
            compatible.sort(key=lambda d: (not d.kell_negative, str(d.id)))
        else:
            rng.shuffle(compatible)
        cohort = compatible[:n_donors_per_bridge]

        for slot, donor in enumerate(cohort):
            if patient is feature and feature_destabilizer and slot == 0:
                # The designated destabilizer for the feature bridge — replaces
                # the Priya hardcoding. Tests can find this donor via
                # `feature_bridge_destabilizer()`.
                donor.response_rate = 0.32
                donor.avg_response_hours = 48.0
                donor.last_donation_date = date.today() - timedelta(days=120)
                donor.total_donations = 2
            m = BridgeMembership(
                bridge_id=bridge.id,
                donor_id=donor.id,
                role=MembershipRole.PRIMARY if slot < 6 else MembershipRole.BACKUP,
                status=MembershipStatus.ACTIVE,
                joined_at=date.today() - timedelta(days=rng.randint(30, 720)),
            )
            db.add(m)
            out.memberships.append(m)

    db.flush()
    return out


def feature_bridge_destabilizer(dataset: TestDataset) -> Donor | None:
    """Return the donor that was set up as the feature bridge's destabilizer.

    Replaces ``next(d for d in members if d.name == 'Priya Sharma')`` in tests.
    The destabilizer is identifiable as the lowest-response_rate active donor
    on the feature bridge.
    """
    if dataset.feature_bridge is None:
        return None
    actives = [
        m.donor for m in dataset.feature_bridge.memberships
        if m.status == MembershipStatus.ACTIVE
    ]
    if not actives:
        return None
    return min(actives, key=lambda d: d.response_rate)


def make_single_patient(
    db: Session,
    *,
    name: str = "Test Patient",
    blood_group: BloodGroup = BloodGroup.B_POS,
    age: int = 8,
    caregiver_name: str = "Test Caregiver",
    caregiver_phone: str = "+919876500001",
    caregiver_relation: CaregiverRelation = CaregiverRelation.MOTHER,
    preferred_language: Language = Language.ENGLISH,
    cadence_days: int = 18,
) -> Patient:
    """Build one Patient + Bridge for unit tests that need a single anchor.
    Returns the persisted Patient (caller can access .bridge)."""
    p = Patient(
        name=name,
        age=age,
        blood_group=blood_group,
        rh_negative=False,
        kell_negative=True,
        city="Hyderabad",
        state="Telangana",
        lat=17.3850,
        lng=78.4867,
        hospital="Test Hospital",
        transfusion_cadence_days=cadence_days,
        last_transfusion_date=date.today() - timedelta(days=12),
        preferred_language=preferred_language,
        caregiver_name=caregiver_name,
        caregiver_phone=caregiver_phone,
        caregiver_relation=caregiver_relation,
        active=True,
    )
    db.add(p)
    db.flush()
    bridge = Bridge(patient_id=p.id, name=f"Bridge for {name}", status=BridgeStatus.ACTIVE)
    db.add(bridge)
    db.flush()
    return p
