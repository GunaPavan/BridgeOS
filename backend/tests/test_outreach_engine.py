"""Tests for the global Alert Allocator — collection, scoring, conflict-resolution.

End-to-end-ish: builds a small synthetic Bridge OS state, runs the cycle,
and asserts on the WaveAllocation output. The math itself is covered by
``test_outreach_scoring`` — these tests focus on the *orchestration* the
engine adds on top of it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Bridge,
    BridgeMembership,
    BridgeStatus,
    Donor,
    MembershipRole,
    MembershipStatus,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    PingResponse,
    UrgencyTier,
)
from app.outreach.engine import (
    collect_open_slots,
    expire_and_escalate_waves,
    materialise_allocation,
    run_cycle,
    score_candidates,
    solve_outreach_cycle,
)


# ---------- builders ----------


def _build_patient(
    db: Session,
    *,
    bg: BloodGroup = BloodGroup.B_POS,
    kell_neg: bool = False,
    last_transfusion_date: date,
    cadence_days: int = 21,
    name: str = "P",
    with_bridge: bool = True,
) -> Patient:
    p = Patient(
        name=name,
        age=12,
        blood_group=bg,
        rh_negative=False,
        kell_negative=kell_neg,
        city="Hyderabad",
        state="Telangana",
        lat=17.39,
        lng=78.46,
        hospital="Apollo",
        transfusion_cadence_days=cadence_days,
        last_transfusion_date=last_transfusion_date,
        active=True,
    )
    db.add(p)
    db.flush()
    if with_bridge:
        b = Bridge(patient_id=p.id, name=f"Bridge for {name}", status=BridgeStatus.ACTIVE)
        db.add(b)
        db.flush()
    return p


def _build_donor(
    db: Session,
    *,
    bg: BloodGroup = BloodGroup.O_POS,
    response_rate: float = 0.7,
    name: str = "D",
    kell_neg: bool = False,
    last_donation_days_ago: int | None = None,
    last_contacted_days_ago: int | None = None,
    total_calls: int = 0,
    lat: float = 17.39,
    lng: float = 78.46,
    today: date | None = None,
) -> Donor:
    today = today or date.today()
    d = Donor(
        name=name,
        age=28,
        blood_group=bg,
        rh_negative=False,
        kell_negative=kell_neg,
        phone="+919999999999",
        city="Hyderabad",
        state="Telangana",
        lat=lat,
        lng=lng,
        is_active=True,
        last_donation_date=(
            today - timedelta(days=last_donation_days_ago)
            if last_donation_days_ago is not None
            else None
        ),
        last_contacted_date=(
            today - timedelta(days=last_contacted_days_ago)
            if last_contacted_days_ago is not None
            else None
        ),
        total_calls=total_calls,
        calls_to_donations_ratio=0.0,
        response_rate=response_rate,
        # Backdate registered_at past the 30-day new-donor grace period so the
        # eligibility filter doesn't reject every synthetic test donor.
        registered_at=datetime.combine(today - timedelta(days=60), datetime.min.time()),
    )
    db.add(d)
    db.flush()
    return d


# ---------- collect_open_slots ----------


class TestCollectOpenSlots:
    def test_picks_up_patient_due_inside_horizon(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        # Last transfusion 19 days ago, cadence 21 → next in 2 days = inside 7d horizon
        _build_patient(
            db_session,
            last_transfusion_date=today - timedelta(days=19),
            cadence_days=21,
            name="due-soon",
        )
        slots = collect_open_slots(db_session, today=today, horizon_days=7)
        assert len(slots) == 1
        assert slots[0].urgency.tier in (UrgencyTier.HIGH, UrgencyTier.MEDIUM)

    def test_skips_planned_slots(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        # Last transfusion 5 days ago, cadence 21 → next in 16 days > horizon
        _build_patient(
            db_session,
            last_transfusion_date=today - timedelta(days=5),
            cadence_days=21,
            name="far-out",
        )
        slots = collect_open_slots(db_session, today=today, horizon_days=7)
        assert slots == []

    def test_skips_patient_with_active_wave_for_same_slot(
        self, db_session: Session
    ) -> None:
        today = date(2026, 6, 6)
        p = _build_patient(
            db_session,
            last_transfusion_date=today - timedelta(days=20),
            cadence_days=21,
            name="already-active",
        )
        next_slot = today + timedelta(days=1)
        existing = OutreachWave(
            patient_id=p.id,
            slot_date=next_slot,
            status=OutreachWaveStatus.ACTIVE,
            tier=OutreachTier.TIER_1,
            urgency=UrgencyTier.CRITICAL,
        )
        db_session.add(existing)
        db_session.flush()
        assert collect_open_slots(db_session, today=today) == []

    def test_inactive_patient_skipped(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        p = _build_patient(
            db_session,
            last_transfusion_date=today - timedelta(days=20),
            cadence_days=21,
            name="inactive",
        )
        p.active = False
        db_session.flush()
        assert collect_open_slots(db_session, today=today) == []


# ---------- score_candidates ----------


class TestScoreCandidates:
    def test_only_eligible_compatible_donors_in_results(
        self, db_session: Session
    ) -> None:
        today = date(2026, 6, 6)
        p = _build_patient(
            db_session,
            bg=BloodGroup.B_POS,
            last_transfusion_date=today - timedelta(days=20),
            name="P-B+",
        )
        # Eligible: O+ (universal donor for B+ via the donor->recipient map)
        eligible = _build_donor(db_session, bg=BloodGroup.O_POS, name="O+ donor", today=today)
        # Incompatible: A+ can't give to B+
        _build_donor(db_session, bg=BloodGroup.A_POS, name="A+ donor", today=today)
        slots = collect_open_slots(db_session, today=today)
        assert len(slots) == 1
        scored = score_candidates(
            slots[0], db=db_session, today=today,
            churn_scores={}, survival_scores={},
        )
        ids = [c.donor.id for c in scored]
        assert eligible.id in ids
        assert len(scored) == 1  # only the eligible one

    def test_results_sorted_by_composite_descending(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        p = _build_patient(
            db_session,
            last_transfusion_date=today - timedelta(days=20),
            name="P",
        )
        far = _build_donor(
            db_session, lat=18.50, lng=78.10, response_rate=0.9,
            name="far high-resp", today=today,
        )
        near = _build_donor(
            db_session, lat=17.40, lng=78.47, response_rate=0.6,
            name="near mid-resp", today=today,
        )
        slots = collect_open_slots(db_session, today=today)
        scored = score_candidates(
            slots[0], db=db_session, today=today,
            churn_scores={}, survival_scores={},
        )
        # Near donor should be in the list (with high distance factor) — the
        # ranking may go either way depending on weights, but both should be present
        # and scored.composite must be monotonically descending.
        composites = [c.composite for c in scored]
        assert composites == sorted(composites, reverse=True)


# ---------- solve_outreach_cycle ----------


class TestSolveCycle:
    def test_per_donor_cap_of_1_across_patients(self, db_session: Session) -> None:
        """Two competing patients should NOT both get pinged to the same donor.

        Replicates Scenario B from the design — patient A and patient B both
        need B+ donors, both top-rank the same 5 candidates, allocator must
        split them.
        """
        today = date(2026, 6, 6)
        a = _build_patient(
            db_session,
            bg=BloodGroup.B_POS,
            last_transfusion_date=today - timedelta(days=20),
            name="patient A",
        )
        b = _build_patient(
            db_session,
            bg=BloodGroup.B_POS,
            last_transfusion_date=today - timedelta(days=20),
            name="patient B",
        )
        # 6 eligible O+ donors
        donors = [
            _build_donor(
                db_session, bg=BloodGroup.O_POS, name=f"donor-{i}",
                response_rate=0.7, today=today,
            )
            for i in range(6)
        ]
        slots = collect_open_slots(db_session, today=today)
        assert len(slots) == 2

        allocations = solve_outreach_cycle(slots, db=db_session, today=today)
        # No donor should appear in both allocations
        a_ids = {d.id for d in allocations[0].donors}
        b_ids = {d.id for d in allocations[1].donors}
        assert not (a_ids & b_ids), "per-donor concurrency cap of 1 violated"

    def test_critical_patient_served_before_medium(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        # Critical patient — due tomorrow
        crit = _build_patient(
            db_session,
            last_transfusion_date=today - timedelta(days=20),
            cadence_days=21,
            name="critical",
        )
        # Medium patient — due in 5 days
        med = _build_patient(
            db_session,
            last_transfusion_date=today - timedelta(days=16),
            cadence_days=21,
            name="medium",
        )
        # Single shared candidate
        d = _build_donor(db_session, today=today, response_rate=0.8)
        slots = collect_open_slots(db_session, today=today)
        assert len(slots) == 2
        allocations = solve_outreach_cycle(slots, db=db_session, today=today)
        # The CRITICAL one should have the donor; MEDIUM should be empty
        crit_alloc = next(a for a in allocations if a.slot.patient.id == crit.id)
        med_alloc = next(a for a in allocations if a.slot.patient.id == med.id)
        assert d.id in [x.id for x in crit_alloc.donors]
        assert d.id not in [x.id for x in med_alloc.donors]

    def test_shortfall_marked_when_pool_too_small(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        _build_patient(
            db_session,
            last_transfusion_date=today - timedelta(days=20),
            name="critical-empty-pool",
        )
        # No compatible donors at all
        slots = collect_open_slots(db_session, today=today)
        allocations = solve_outreach_cycle(slots, db=db_session, today=today)
        assert len(allocations) == 1
        assert not allocations[0].fully_covered
        assert allocations[0].donors == []


# ---------- materialise + run_cycle ----------


class TestMaterialise:
    def test_materialise_persists_wave_and_pings(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        p = _build_patient(
            db_session,
            last_transfusion_date=today - timedelta(days=20),
            name="m-test",
        )
        for i in range(3):
            _build_donor(db_session, name=f"d-{i}", today=today)
        slots = collect_open_slots(db_session, today=today)
        allocations = solve_outreach_cycle(slots, db=db_session, today=today)
        wave = materialise_allocation(allocations[0], db=db_session, today=today)
        db_session.commit()

        # Reload to verify persistence
        stored = db_session.get(OutreachWave, wave.id)
        assert stored is not None
        assert stored.status == OutreachWaveStatus.ACTIVE
        assert stored.tier == OutreachTier.TIER_1
        assert len(stored.pings) == len(allocations[0].donors)
        assert all(p.response == PingResponse.PENDING for p in stored.pings)


class TestRunCycleEndToEnd:
    def test_dry_run_does_not_persist(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        _build_patient(
            db_session,
            last_transfusion_date=today - timedelta(days=20),
            name="dr",
        )
        for i in range(4):
            _build_donor(db_session, name=f"d-{i}", today=today)
        summary, allocations = run_cycle(db_session, today=today, dry_run=True)
        assert summary.dry_run is True
        # No waves should have been created
        waves = db_session.execute(
            __import__("sqlalchemy").select(OutreachWave)
        ).scalars().all()
        assert len(waves) == 0

    def test_real_run_persists_and_returns_summary(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        _build_patient(
            db_session,
            last_transfusion_date=today - timedelta(days=20),
            name="r-1",
        )
        _build_patient(
            db_session,
            last_transfusion_date=today - timedelta(days=20),
            name="r-2",
        )
        for i in range(8):
            _build_donor(db_session, name=f"d-{i}", today=today)
        summary, allocations = run_cycle(db_session, today=today, dry_run=False)
        assert summary.dry_run is False
        assert summary.open_slots == 2
        assert summary.waves_created >= 1
        # Pings should now exist
        pings = db_session.execute(
            __import__("sqlalchemy").select(OutreachPing)
        ).scalars().all()
        assert len(pings) == summary.pings_planned


class TestExpireAndEscalate:
    def test_expires_past_due_active_waves(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        p = _build_patient(
            db_session,
            last_transfusion_date=today - timedelta(days=20),
            name="e-test",
        )
        past = datetime.utcnow() - timedelta(hours=1)
        future = datetime.utcnow() + timedelta(hours=1)
        stale = OutreachWave(
            patient_id=p.id,
            slot_date=today + timedelta(days=1),
            status=OutreachWaveStatus.ACTIVE,
            tier=OutreachTier.TIER_1,
            urgency=UrgencyTier.CRITICAL,
            expires_at=past,
        )
        fresh = OutreachWave(
            patient_id=p.id,
            slot_date=today + timedelta(days=5),
            status=OutreachWaveStatus.ACTIVE,
            tier=OutreachTier.TIER_1,
            urgency=UrgencyTier.MEDIUM,
            expires_at=future,
        )
        db_session.add_all([stale, fresh])
        db_session.flush()
        expired = expire_and_escalate_waves(db_session)
        assert {w.id for w in expired} == {stale.id}
        db_session.refresh(stale)
        db_session.refresh(fresh)
        assert stale.status == OutreachWaveStatus.EXPIRED
        assert fresh.status == OutreachWaveStatus.ACTIVE
