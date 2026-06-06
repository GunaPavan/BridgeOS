"""Phase E — emergency mode tests.

Reach-window math + trigger_emergency end-to-end. The audit row, the
EMERGENCY-tier wave, the pool counts, and the "donors outside reach are
excluded" behaviour.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    Donor,
    EmergencyEvent,
    EmergencyEventStatus,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
)
from app.outreach.emergency import (
    can_reach_in_time,
    estimate_travel_min,
    find_reachable_donors,
    trigger_emergency,
)


def _patient(db: Session, *, with_bridge: bool = True) -> Patient:
    p = Patient(
        name="EmergencyTest Patient",
        age=15,
        blood_group=BloodGroup.B_POS,
        rh_negative=False,
        kell_negative=False,
        city="Hyderabad",
        state="Telangana",
        lat=17.39,
        lng=78.46,
        hospital="Apollo",
        transfusion_cadence_days=21,
        last_transfusion_date=date(2026, 5, 15),
        active=True,
    )
    db.add(p)
    db.flush()
    if with_bridge:
        db.add(Bridge(patient_id=p.id, name="Bridge", status=BridgeStatus.ACTIVE))
        db.flush()
    return p


def _donor(
    db: Session, *, name: str, lat: float, lng: float,
    bg: BloodGroup = BloodGroup.O_POS, is_active: bool = True,
) -> Donor:
    d = Donor(
        name=name,
        age=30,
        blood_group=bg,
        rh_negative=False,
        kell_negative=False,
        phone=f"+9199999{abs(hash(name)) % 99999:05d}",
        city="Hyderabad",
        state="Telangana",
        lat=lat,
        lng=lng,
        is_active=is_active,
        response_rate=0.7,
        registered_at=datetime(2025, 1, 1),
    )
    db.add(d)
    db.flush()
    return d


# ---------- pure math ----------


class TestReachMath:
    def test_5km_at_25kmh_is_12_minutes(self) -> None:
        assert estimate_travel_min(5.0) == pytest.approx(12.0)

    def test_negative_distance_is_zero(self) -> None:
        assert estimate_travel_min(-1) == 0.0

    def test_can_reach_within_window(self) -> None:
        # 5 km away, deadline 2 hours out — easy
        now = datetime(2026, 6, 6, 12, 0, 0)
        deadline = now + timedelta(hours=2)
        assert can_reach_in_time(5.0, deadline_at=deadline, now=now) is True

    def test_cant_reach_after_deadline(self) -> None:
        now = datetime(2026, 6, 6, 12, 0, 0)
        deadline = now + timedelta(minutes=10)  # too soon
        assert can_reach_in_time(20.0, deadline_at=deadline, now=now) is False

    def test_reach_just_enough(self) -> None:
        # 5 km at 25 km/h = 12 min travel + 30 min prep = 42 min. Deadline 60 → ok
        now = datetime(2026, 6, 6, 12, 0, 0)
        deadline = now + timedelta(minutes=60)
        assert can_reach_in_time(5.0, deadline_at=deadline, now=now) is True


# ---------- find_reachable_donors ----------


class TestFindReachable:
    def test_excludes_donors_outside_reach_window(self, db_session: Session) -> None:
        p = _patient(db_session)
        # Donor 1 — 5 km away, inside reach
        near = _donor(db_session, name="Near", lat=17.40, lng=78.48)
        # Donor 2 — 100 km away, outside reach with a 30-min deadline
        far = _donor(db_session, name="Far", lat=18.30, lng=78.10)
        now = datetime(2026, 6, 6, 12, 0, 0)
        deadline = now + timedelta(minutes=45)  # ~3 km of travel possible
        result = find_reachable_donors(
            db_session,
            patient=p,
            hospital_lat=p.lat,
            hospital_lng=p.lng,
            deadline_at=deadline,
            now=now,
        )
        # Near donor is in 5km range — but at 12min travel + 30min prep = 42min,
        # and deadline is 45min → IN
        ids = [r.donor.id for r in result]
        assert near.id in ids
        assert far.id not in ids

    def test_excludes_incompatible_blood_group(self, db_session: Session) -> None:
        p = _patient(db_session)  # B+
        # A+ donor can't give to B+
        _donor(db_session, name="Wrong group", lat=17.40, lng=78.46, bg=BloodGroup.A_POS)
        # O+ donor can
        ok = _donor(db_session, name="Correct group", lat=17.40, lng=78.46)
        result = find_reachable_donors(
            db_session, patient=p, hospital_lat=p.lat, hospital_lng=p.lng,
            deadline_at=datetime.utcnow() + timedelta(hours=2),
        )
        ids = [r.donor.id for r in result]
        assert ok.id in ids
        assert len(result) == 1

    def test_sorts_by_distance_ascending(self, db_session: Session) -> None:
        p = _patient(db_session)
        # Build 3 donors at increasing distances
        d_closest = _donor(db_session, name="Closest", lat=17.40, lng=78.46)
        d_mid = _donor(db_session, name="Mid", lat=17.45, lng=78.46)
        d_far = _donor(db_session, name="Far", lat=17.49, lng=78.46)
        result = find_reachable_donors(
            db_session, patient=p, hospital_lat=p.lat, hospital_lng=p.lng,
            deadline_at=datetime.utcnow() + timedelta(hours=4),
        )
        # First in list should be the closest
        assert result[0].donor.id == d_closest.id


# ---------- trigger_emergency end-to-end ----------


class TestTriggerEmergency:
    def test_creates_audit_event_and_emergency_wave(self, db_session: Session) -> None:
        p = _patient(db_session)
        for i in range(3):
            _donor(db_session, name=f"Reachable {i}", lat=17.40, lng=78.46 + 0.01 * i)
        now = datetime(2026, 6, 6, 12, 0, 0)
        result = trigger_emergency(
            db_session,
            patient_id=p.id,
            coordinator_name="Aakash J",
            transfusion_deadline_at=now + timedelta(hours=2),
            justification="Severe haemoglobin drop; needs immediate transfusion.",
            now=now,
        )
        assert result.event.id is not None
        assert result.wave is not None
        # Wave is at EMERGENCY tier
        assert result.wave.tier == OutreachTier.EMERGENCY
        # Pings created — one per reachable donor
        pings = db_session.execute(
            select(OutreachPing).where(OutreachPing.wave_id == result.wave.id)
        ).scalars().all()
        assert len(pings) == 3
        # Audit captures the coordinator, justification, hospital
        assert result.event.triggered_by == "Aakash J"
        assert "haemoglobin" in result.event.justification
        assert result.event.hospital_name == p.hospital
        assert result.event.wave_id == result.wave.id

    def test_no_reachable_donors_creates_event_but_no_wave(self, db_session: Session) -> None:
        p = _patient(db_session)
        # No donors at all → reachable_count = 0
        now = datetime(2026, 6, 6, 12, 0, 0)
        result = trigger_emergency(
            db_session,
            patient_id=p.id,
            coordinator_name="Coord",
            transfusion_deadline_at=now + timedelta(hours=2),
            justification="—",
            now=now,
        )
        assert result.event.id is not None
        assert result.wave is None
        assert result.reachable_count == 0

    def test_emergency_waives_total_calls_fatigue_gate(self, db_session: Session) -> None:
        """In emergency mode, even high-call-count donors are eligible."""
        p = _patient(db_session)
        # This donor would normally be excluded (total_calls=15 hits fatigue gate)
        burnt = _donor(db_session, name="Burnt", lat=17.40, lng=78.46)
        burnt.total_calls = 15
        db_session.flush()
        now = datetime(2026, 6, 6, 12, 0, 0)
        result = trigger_emergency(
            db_session,
            patient_id=p.id,
            coordinator_name="Coord",
            transfusion_deadline_at=now + timedelta(hours=2),
            justification="—",
            now=now,
        )
        # Burnt donor should appear in the wave
        assert result.wave is not None
        ping_donor_ids = [p.donor_id for p in result.wave.pings]
        assert burnt.id in ping_donor_ids

    def test_emergency_does_NOT_waive_90day_clinical_deferral(self, db_session: Session) -> None:
        """Clinical safety is non-negotiable, even in emergency."""
        p = _patient(db_session)
        recent = _donor(db_session, name="Recently donated", lat=17.40, lng=78.46)
        recent.last_donation_date = date.today() - timedelta(days=30)
        db_session.flush()
        now = datetime.utcnow()
        result = trigger_emergency(
            db_session,
            patient_id=p.id,
            coordinator_name="Coord",
            transfusion_deadline_at=now + timedelta(hours=2),
            justification="—",
            now=now,
        )
        # Should NOT include the recent-donor
        if result.wave is not None:
            ping_donor_ids = [p.donor_id for p in result.wave.pings]
            assert recent.id not in ping_donor_ids

    def test_past_deadline_raises(self, db_session: Session) -> None:
        p = _patient(db_session)
        now = datetime(2026, 6, 6, 12, 0, 0)
        with pytest.raises(ValueError, match="Deadline already passed"):
            trigger_emergency(
                db_session,
                patient_id=p.id,
                coordinator_name="Coord",
                transfusion_deadline_at=now - timedelta(hours=1),
                justification="—",
                now=now,
            )
