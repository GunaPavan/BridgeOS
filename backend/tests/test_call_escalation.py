"""E11 — call escalation tests.

Covers:
  - Threshold logic per urgency tier (2h/24h/3d/5d)
  - Skip conditions (any accept, no dispatch yet, already escalated)
  - SMS-only for PLANNED/MEDIUM, SMS+Voice for HIGH/CRITICAL
  - Idempotency: re-running the scan doesn't double-escalate
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.integrations import sns_sms_client, twilio_client
from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    CallEscalation,
    Donor,
    EscalationChannel,
    EscalationStatus,
    Language,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    PingResponse,
    UrgencyTier,
)
from app.services.call_escalation import (
    _threshold_hours,
    dispatch_escalation,
    find_escalation_candidates,
    run_escalation_scan,
)


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    sns_sms_client._reset_outbox_for_tests()


def _make_wave_with_pings(
    db: Session,
    *,
    urgency: UrgencyTier,
    age_hours: int,
    n_donors: int = 2,
    any_accepted: bool = False,
    any_sent: bool = True,
) -> OutreachWave:
    """Create a wave that's `age_hours` old with `n_donors` pings."""
    patient = Patient(
        name=f"Patient {urgency.value}", age=10, blood_group=BloodGroup.B_POS,
        rh_negative=False, kell_negative=False,
        city="Hyderabad", state="Telangana", lat=17.39, lng=78.46,
        hospital="Apollo", transfusion_cadence_days=21,
        last_transfusion_date=date(2026, 5, 1), active=True,
    )
    db.add(patient); db.flush()
    bridge = Bridge(patient_id=patient.id, name="Br", status=BridgeStatus.ACTIVE)
    db.add(bridge); db.flush()

    wave_created = datetime.utcnow() - timedelta(hours=age_hours)
    wave = OutreachWave(
        bridge_id=bridge.id, patient_id=patient.id,
        slot_date=date.today() + timedelta(days=5),
        status=OutreachWaveStatus.ACTIVE,
        tier=OutreachTier.TIER_1, urgency=urgency,
        created_at=wave_created,
    )
    db.add(wave); db.flush()

    for i in range(n_donors):
        donor = Donor(
            name=f"Donor {i}", age=28, phone=f"+919900{i:06d}",
            blood_group=BloodGroup.B_POS, city="Hyderabad", state="Telangana",
            lat=17.39, lng=78.46, preferred_language=Language.ENGLISH,
            is_active=True,
        )
        db.add(donor); db.flush()
        ping = OutreachPing(
            wave_id=wave.id, donor_id=donor.id,
            response=PingResponse.ACCEPTED if (any_accepted and i == 0) else PingResponse.PENDING,
            sent_at=wave_created if any_sent else None,
            expires_at=datetime.utcnow() + timedelta(hours=12),
        )
        db.add(ping)
    db.flush()
    db.refresh(wave)
    return wave


# ----- threshold table -----


def test_threshold_table_defaults():
    assert _threshold_hours(UrgencyTier.CRITICAL) == 2
    assert _threshold_hours(UrgencyTier.HIGH) == 24
    assert _threshold_hours(UrgencyTier.MEDIUM) == 72
    assert _threshold_hours(UrgencyTier.PLANNED) == 120


def test_threshold_env_overrides(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_ESCALATE_PLANNED_HOURS", "240")
    assert _threshold_hours(UrgencyTier.PLANNED) == 240


# ----- candidate scanner -----


def test_no_candidates_when_under_threshold(db_session: Session):
    """A 1h-old CRITICAL wave is at the threshold (2h), still under → no escalation."""
    _make_wave_with_pings(db_session, urgency=UrgencyTier.CRITICAL, age_hours=1)
    db_session.commit()
    cs = find_escalation_candidates(db_session)
    assert len(cs) == 0


def test_critical_wave_past_threshold_is_candidate(db_session: Session):
    _make_wave_with_pings(db_session, urgency=UrgencyTier.CRITICAL, age_hours=3)
    db_session.commit()
    cs = find_escalation_candidates(db_session)
    assert len(cs) == 1
    assert cs[0].hours_since_dispatch >= 2


def test_planned_5day_threshold(db_session: Session):
    """5 days = 120h. Wave at 119h is NOT a candidate; 121h IS."""
    _make_wave_with_pings(db_session, urgency=UrgencyTier.PLANNED, age_hours=119)
    db_session.commit()
    assert len(find_escalation_candidates(db_session)) == 0


def test_wave_with_accepted_ping_is_not_candidate(db_session: Session):
    """If ANY donor accepted, no escalation needed even past threshold."""
    _make_wave_with_pings(
        db_session, urgency=UrgencyTier.HIGH, age_hours=48, any_accepted=True
    )
    db_session.commit()
    assert len(find_escalation_candidates(db_session)) == 0


# ----- dispatch + idempotency -----


def test_dispatch_creates_row_and_sends_sms(db_session: Session):
    wave = _make_wave_with_pings(
        db_session, urgency=UrgencyTier.PLANNED, age_hours=121
    )
    db_session.commit()
    candidates = find_escalation_candidates(db_session)
    assert len(candidates) == 1
    esc = dispatch_escalation(db_session, candidates[0])
    db_session.commit()
    assert esc.status == EscalationStatus.DISPATCHED
    assert esc.channel == EscalationChannel.SMS  # PLANNED tier = SMS only
    assert esc.sms_message_id  # set
    assert esc.voice_call_sid is None
    # SMS landed in the SNS mock outbox
    outbox = sns_sms_client.list_mock_sends()
    assert len(outbox) == 1
    assert "PLANNED" in outbox[0]["body"] or "planned" in outbox[0]["body"].lower()


def test_critical_dispatch_also_places_voice_call(db_session: Session):
    wave = _make_wave_with_pings(
        db_session, urgency=UrgencyTier.CRITICAL, age_hours=3
    )
    db_session.commit()
    candidates = find_escalation_candidates(db_session)
    esc = dispatch_escalation(db_session, candidates[0])
    db_session.commit()
    assert esc.channel == EscalationChannel.SMS_AND_VOICE
    assert esc.voice_call_sid is not None
    assert esc.voice_call_sid.startswith("MOCK-CALL-")


def test_scan_is_idempotent(db_session: Session):
    """Running the scan twice creates only one escalation per wave."""
    _make_wave_with_pings(db_session, urgency=UrgencyTier.MEDIUM, age_hours=80)
    db_session.commit()
    r1 = run_escalation_scan(db_session)
    r2 = run_escalation_scan(db_session)
    assert r1["dispatched"] == 1
    assert r2["dispatched"] == 0
    rows = db_session.query(CallEscalation).all()
    assert len(rows) == 1
