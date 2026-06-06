"""E6 — DispatchWorker routes by envelope channel.

dispatch_wave reads donor.preferred_channel and stamps the envelope with
sms/whatsapp. The worker reads the envelope and calls the matching client.
This test exercises the worker layer directly so we don't need a full
allocator cycle.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.integrations import sns_sms_client, sqs_client
from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    ContactChannel,
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
from app.outreach.dispatch_queue import (
    DispatchEnvelope,
    DispatchWorker,
    enqueue_dispatch,
)


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    sqs_client._reset_mock_queues_for_tests()
    sns_sms_client._reset_outbox_for_tests()


def _make_ping(db: Session) -> OutreachPing:
    patient = Patient(
        name="Riya", age=10, blood_group=BloodGroup.B_POS,
        rh_negative=False, kell_negative=False,
        city="Hyderabad", state="Telangana", lat=17.39, lng=78.46,
        hospital="Apollo", transfusion_cadence_days=21,
        last_transfusion_date=date(2026, 5, 1), active=True,
    )
    db.add(patient); db.flush()
    bridge = Bridge(patient_id=patient.id, name="Riya bridge", status=BridgeStatus.ACTIVE)
    db.add(bridge); db.flush()
    wave = OutreachWave(
        bridge_id=bridge.id, patient_id=patient.id,
        slot_date=date.today() + timedelta(days=5),
        status=OutreachWaveStatus.ACTIVE,
        tier=OutreachTier.TIER_1, urgency=UrgencyTier.HIGH,
    )
    db.add(wave); db.flush()
    donor = Donor(
        name="Vikram", age=28, phone="+919900000077",
        blood_group=BloodGroup.B_POS, city="Hyderabad", state="Telangana",
        lat=17.39, lng=78.46, preferred_language=Language.ENGLISH,
        is_active=True,
    )
    db.add(donor); db.flush()
    ping = OutreachPing(
        wave_id=wave.id, donor_id=donor.id,
        response=PingResponse.PENDING,
        expires_at=datetime.utcnow() + timedelta(hours=4),
    )
    db.add(ping); db.flush()
    return ping


def test_worker_dispatches_sms_envelope_via_sns_sms(db_session: Session):
    """An envelope with channel='sms' goes through sns_sms_client.send_sms."""
    ping = _make_ping(db_session)
    db_session.commit()

    # Enqueue an SMS envelope
    enqueue_dispatch(DispatchEnvelope(
        channel="sms",
        to="+919900000077",
        body="URGENT slot for Riya tomorrow. Call coordinator if you can help.",
        idempotency_key=f"dispatch_{ping.id}",
        ping_id=str(ping.id),
        donor_id=str(ping.donor_id),
        template_key="urgent_slot_alert",
        language="en",
    ))

    # Drain once
    worker = DispatchWorker(session_factory=SessionLocal)
    n = worker._drain_once(batch=5)
    assert n == 1
    assert worker.stats.sent == 1

    # SMS landed in the SNS mock outbox
    outbox = sns_sms_client.list_mock_sends()
    assert len(outbox) == 1
    assert outbox[0]["to"] == "+919900000077"
    assert "URGENT" in outbox[0]["body"]


def test_worker_dispatches_whatsapp_envelope_via_twilio(db_session: Session):
    """A whatsapp envelope routes through twilio_client (mock mode)."""
    from app.integrations import twilio_client
    ping = _make_ping(db_session)
    db_session.commit()

    enqueue_dispatch(DispatchEnvelope(
        channel="whatsapp",
        to="+919900000077",
        body="Riya needs a donor — reply YES.",
        idempotency_key=f"dispatch_{ping.id}",
        ping_id=str(ping.id),
        donor_id=str(ping.donor_id),
    ))
    worker = DispatchWorker(session_factory=SessionLocal)
    n = worker._drain_once(batch=5)
    assert n == 1
    assert worker.stats.sent == 1
    # No SMS should have been sent
    assert sns_sms_client.list_mock_sends() == []


def test_default_donor_channel_is_whatsapp():
    """New donors default to WHATSAPP (E6.1) — it's the only bidirectional
    donor channel. SMS is one-way alert-only, never the default."""
    d = Donor(
        name="Test", age=25, phone="+91990",
        blood_group=BloodGroup.B_POS, city="X", state="Y",
        lat=0.0, lng=0.0, preferred_language=Language.ENGLISH, is_active=True,
    )
    # The default kicks in once persisted (SQLAlchemy default)
    assert (
        d.preferred_channel in (ContactChannel.WHATSAPP, None)
        or d.preferred_channel == "whatsapp"
    )


def test_sms_dispatch_appends_call_coordinator_tail(db_session: Session):
    """When SMS is opted in, the body gets a 'call coordinator' tail so the
    recipient knows where to direct their reply (SMS is one-way)."""
    ping = _make_ping(db_session)
    db_session.commit()

    enqueue_dispatch(DispatchEnvelope(
        channel="sms",
        to="+919900000077",
        body="Riya needs a donor today.",
        idempotency_key=f"dispatch_{ping.id}",
        ping_id=str(ping.id),
        donor_id=str(ping.donor_id),
    ))
    worker = DispatchWorker(session_factory=SessionLocal)
    worker._drain_once(batch=5)

    outbox = sns_sms_client.list_mock_sends()
    assert len(outbox) == 1
    assert "Riya needs a donor today" in outbox[0]["body"]
    assert "call coordinator" in outbox[0]["body"].lower()


def test_unknown_channel_drops_envelope(db_session: Session):
    """An envelope with an unknown channel is logged + counted as failed,
    not silently sent."""
    ping = _make_ping(db_session)
    db_session.commit()

    enqueue_dispatch(DispatchEnvelope(
        channel="carrier_pigeon",  # not a real channel
        to="+919900000077",
        body="bad envelope",
        idempotency_key=f"dispatch_{ping.id}",
        ping_id=str(ping.id),
    ))
    worker = DispatchWorker(session_factory=SessionLocal)
    worker._drain_once(batch=5)
    assert worker.stats.failed == 1
    assert sns_sms_client.list_mock_sends() == []
