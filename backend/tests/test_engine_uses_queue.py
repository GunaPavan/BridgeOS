"""Phase E3 — confirm dispatch_wave routes through SQS by default.

Until Phase E3 the allocator called twilio_client.send_whatsapp() inline
inside the loop, so a Twilio latency spike blocked the whole allocator
cycle. After E3, ``dispatch_wave`` enqueues each ping to SQS and the
DispatchWorker thread drains the queue independently.

The env var ``BRIDGE_OS_DISPATCH_INLINE=1`` preserves the legacy synchronous
path (used by the bulk re-ingest script and a handful of older tests).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.integrations import sqs_client
from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    Donor,
    Language,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    PingResponse,
    UrgencyTier,
)
from app.outreach.dispatch import dispatch_wave, make_slot_ref


def _build_wave_with_pings(db: Session, *, n_donors: int = 2) -> OutreachWave:
    patient = Patient(
        name="Test Patient",
        age=10,
        blood_group=BloodGroup.B_POS,
        rh_negative=False,
        kell_negative=False,
        city="Hyderabad",
        state="Telangana",
        lat=17.39,
        lng=78.46,
        hospital="Apollo",
        transfusion_cadence_days=21,
        last_transfusion_date=date(2026, 5, 1),
        active=True,
    )
    db.add(patient)
    db.flush()
    bridge = Bridge(patient_id=patient.id, name="Test Bridge", status=BridgeStatus.ACTIVE)
    db.add(bridge)
    db.flush()
    wave = OutreachWave(
        bridge_id=bridge.id,
        patient_id=patient.id,
        slot_date=date.today() + timedelta(days=5),
        status=OutreachWaveStatus.ACTIVE,
        tier=OutreachTier.TIER_1,
        urgency=UrgencyTier.HIGH,
    )
    db.add(wave)
    db.flush()
    for i in range(n_donors):
        donor = Donor(
            name=f"Donor {i}",
            age=28,
            phone=f"+91900000{1000+i:04d}",
            blood_group=BloodGroup.B_POS,
            city="Hyderabad",
            state="Telangana",
            lat=17.39 + 0.01 * i,
            lng=78.46,
            preferred_language=Language.ENGLISH,
            is_active=True,
        )
        db.add(donor)
        db.flush()
        ping = OutreachPing(
            wave_id=wave.id,
            donor_id=donor.id,
            response=PingResponse.PENDING,
            expires_at=datetime.utcnow() + timedelta(hours=4),
        )
        db.add(ping)
    db.flush()
    db.refresh(wave)
    return wave


@pytest.fixture
def _no_quiet_hours(monkeypatch):
    """Force is_quiet_hours() False so the test isn't time-of-day sensitive."""
    from app.outreach import dispatch as _disp
    monkeypatch.setattr(_disp, "is_quiet_hours", lambda *a, **kw: False)


@pytest.fixture(autouse=True)
def _reset_sqs(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    monkeypatch.delenv("BRIDGE_OS_DISPATCH_INLINE", raising=False)
    sqs_client._reset_mock_queues_for_tests()


def test_dispatch_wave_enqueues_to_sqs_by_default(db_session: Session, _no_quiet_hours):
    """Without BRIDGE_OS_DISPATCH_INLINE set, every PENDING ping should
    land on the SQS dispatch queue rather than calling Twilio inline."""
    wave = _build_wave_with_pings(db_session, n_donors=2)
    assert sqs_client.queue_depth()["primary"] == 0

    dispatch_wave(wave, db=db_session)

    depth = sqs_client.queue_depth()
    assert depth["primary"] == 2, (
        f"Expected 2 messages enqueued (one per donor), got {depth}"
    )


def test_inline_env_var_bypasses_sqs(
    db_session: Session, monkeypatch, _no_quiet_hours
):
    """BRIDGE_OS_DISPATCH_INLINE=1 forces the legacy synchronous Twilio
    path; no SQS messages should be enqueued."""
    monkeypatch.setenv("BRIDGE_OS_DISPATCH_INLINE", "1")
    wave = _build_wave_with_pings(db_session, n_donors=2)

    dispatch_wave(wave, db=db_session)

    assert sqs_client.queue_depth()["primary"] == 0
    # Pings should have whatsapp_sid stamped (from Twilio's mock SID)
    sids = [p.whatsapp_sid for p in wave.pings]
    assert all(s is not None for s in sids), f"sids: {sids}"


def test_enqueued_envelope_includes_ping_id(db_session: Session, _no_quiet_hours):
    """The envelope must carry the ping_id so the worker can stamp the ping
    once delivery confirms.

    E6 note: the channel comes from donor.preferred_channel (default SMS).
    This test only cares about the ping_id + to fields being preserved;
    channel routing has dedicated coverage in test_dispatch_routes_by_channel.
    """
    wave = _build_wave_with_pings(db_session, n_donors=1)
    dispatch_wave(wave, db=db_session)

    msgs = sqs_client.receive_messages(max_messages=10)
    assert len(msgs) == 1
    assert "ping_id" in msgs[0].body
    # Channel reflects the donor's preference — default = SMS
    assert msgs[0].body["channel"] in {"sms", "whatsapp"}
    assert msgs[0].body["to"].startswith("+91")
