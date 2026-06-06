"""Tests for SQLAlchemy ORM models and their derived properties."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Bridge,
    BridgeHealth,
    BridgeMembership,
    BridgeStatus,
    Donor,
    MembershipStatus,
    Patient,
)


def _make_patient(session: Session, **kwargs) -> Patient:
    defaults = dict(
        name="Aarav Reddy",
        age=8,
        blood_group=BloodGroup.B_POS,
        rh_negative=False,
        kell_negative=True,
        city="Hyderabad",
        state="Telangana",
        lat=17.385,
        lng=78.4867,
        hospital="Apollo Hospitals",
        transfusion_cadence_days=18,
        last_transfusion_date=date.today() - timedelta(days=12),
    )
    defaults.update(kwargs)
    p = Patient(**defaults)
    session.add(p)
    session.flush()
    return p


def _make_donor(session: Session, suffix: str = "1", **kwargs) -> Donor:
    defaults = dict(
        name=f"Donor {suffix}",
        age=28,
        blood_group=BloodGroup.O_POS,
        rh_negative=False,
        kell_negative=False,
        phone=f"+9198000000{suffix.zfill(2)}",
        city="Hyderabad",
        state="Telangana",
        lat=17.385,
        lng=78.4867,
    )
    defaults.update(kwargs)
    d = Donor(**defaults)
    session.add(d)
    session.flush()
    return d


def test_patient_next_transfusion_date_computed(db_session: Session) -> None:
    p = _make_patient(db_session, last_transfusion_date=date(2026, 5, 1), transfusion_cadence_days=18)
    assert p.next_transfusion_date == date(2026, 5, 19)


def test_patient_next_transfusion_none_if_no_history(db_session: Session) -> None:
    p = _make_patient(db_session, last_transfusion_date=None)
    assert p.next_transfusion_date is None
    assert p.days_until_transfusion is None


def test_donor_eligibility_respects_90_day_window(db_session: Session) -> None:
    recent = _make_donor(db_session, suffix="r", last_donation_date=date.today() - timedelta(days=40))
    far = _make_donor(db_session, suffix="f", last_donation_date=date.today() - timedelta(days=120))
    fresh = _make_donor(db_session, suffix="n", last_donation_date=None)
    assert not recent.is_eligible_to_donate
    assert far.is_eligible_to_donate
    assert fresh.is_eligible_to_donate


def test_bridge_health_stable_with_8_donors(db_session: Session) -> None:
    p = _make_patient(db_session)
    bridge = Bridge(patient_id=p.id, name=f"Bridge for {p.name}", status=BridgeStatus.ACTIVE)
    db_session.add(bridge)
    db_session.flush()
    for i in range(8):
        donor = _make_donor(db_session, suffix=str(i))
        db_session.add(
            BridgeMembership(bridge_id=bridge.id, donor_id=donor.id, status=MembershipStatus.ACTIVE)
        )
    db_session.flush()
    db_session.refresh(bridge)
    assert bridge.active_donor_count == 8
    assert bridge.health == BridgeHealth.STABLE


def test_bridge_health_at_risk_with_5_to_7_donors(db_session: Session) -> None:
    p = _make_patient(db_session)
    bridge = Bridge(patient_id=p.id, name=f"Bridge for {p.name}", status=BridgeStatus.ACTIVE)
    db_session.add(bridge)
    db_session.flush()
    for i in range(6):
        donor = _make_donor(db_session, suffix=str(i))
        db_session.add(
            BridgeMembership(bridge_id=bridge.id, donor_id=donor.id, status=MembershipStatus.ACTIVE)
        )
    db_session.flush()
    db_session.refresh(bridge)
    assert bridge.health == BridgeHealth.AT_RISK


def test_bridge_health_critical_with_fewer_than_5(db_session: Session) -> None:
    p = _make_patient(db_session)
    bridge = Bridge(patient_id=p.id, name=f"Bridge for {p.name}", status=BridgeStatus.ACTIVE)
    db_session.add(bridge)
    db_session.flush()
    for i in range(3):
        donor = _make_donor(db_session, suffix=str(i))
        db_session.add(
            BridgeMembership(bridge_id=bridge.id, donor_id=donor.id, status=MembershipStatus.ACTIVE)
        )
    db_session.flush()
    db_session.refresh(bridge)
    assert bridge.health == BridgeHealth.CRITICAL


def test_bridge_only_counts_active_memberships(db_session: Session) -> None:
    p = _make_patient(db_session)
    bridge = Bridge(patient_id=p.id, name=f"Bridge for {p.name}", status=BridgeStatus.ACTIVE)
    db_session.add(bridge)
    db_session.flush()
    for i in range(10):
        donor = _make_donor(db_session, suffix=str(i))
        status_val = MembershipStatus.ACTIVE if i < 5 else MembershipStatus.EXITED
        db_session.add(BridgeMembership(bridge_id=bridge.id, donor_id=donor.id, status=status_val))
    db_session.flush()
    db_session.refresh(bridge)
    assert bridge.total_donor_count == 10
    assert bridge.active_donor_count == 5
    assert bridge.health == BridgeHealth.AT_RISK
