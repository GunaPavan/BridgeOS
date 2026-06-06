"""Phase E3 — DispatchWorker draining + idempotency tests."""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    Donor,
    EmailMessage,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    PingResponse,
    UrgencyTier,
    WhatsAppMessage,
)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    from app.integrations import sqs_client
    sqs_client._reset_mock_queues_for_tests()
    yield


class _NoCloseSession:
    def __init__(self, session: Session) -> None:
        self._s = session

    def __enter__(self) -> Session:
        return self._s

    def __exit__(self, *args) -> None:
        return None


@pytest.fixture
def session_factory(db_session: Session):
    return lambda: _NoCloseSession(db_session)


@pytest.fixture
def mock_twilio(monkeypatch):
    calls = []

    class _Result:
        sid = "fake-sid"
        status = "queued"

    def _fake_send(*, to_number: str, body: str):
        calls.append({"to": to_number, "body": body})
        return _Result()

    monkeypatch.setattr(
        "app.integrations.twilio_client.send_whatsapp", _fake_send
    )
    monkeypatch.setattr(
        "app.integrations.twilio_client.whatsapp_from", lambda: "+10000000"
    )
    return calls


def _make_ping(db: Session) -> OutreachPing:
    p = Patient(
        name="P", age=10, blood_group=BloodGroup.O_POS,
        rh_negative=False, kell_negative=False,
        city="Hyderabad", state="Telangana", lat=17.4, lng=78.5,
        hospital="Apollo", transfusion_cadence_days=21,
        last_transfusion_date=date(2026, 5, 15), active=True,
    )
    db.add(p); db.flush()
    b = Bridge(patient_id=p.id, name="B", status=BridgeStatus.ACTIVE)
    db.add(b); db.flush()
    w = OutreachWave(
        patient_id=p.id, bridge_id=b.id, slot_date=date(2026, 6, 8),
        tier=OutreachTier.TIER_1, urgency=UrgencyTier.CRITICAL,
        status=OutreachWaveStatus.ACTIVE, target_p_accept=0.95,
        gap_days_at_creation=2,
    )
    db.add(w); db.flush()
    d = Donor(
        name="D", age=29, blood_group=BloodGroup.O_POS,
        rh_negative=False, kell_negative=False, phone="+919999990001",
        city="Hyderabad", state="Telangana", lat=17.4, lng=78.5,
        is_active=True, response_rate=0.6, registered_at=datetime(2025, 1, 1),
    )
    db.add(d); db.flush()
    ping = OutreachPing(
        wave_id=w.id, donor_id=d.id, response=PingResponse.PENDING,
        sent_at=datetime.utcnow(),
    )
    db.add(ping); db.flush()
    return ping


def test_worker_drains_whatsapp_envelope(
    db_session: Session, session_factory, mock_twilio
):
    from app.integrations import sqs_client
    from app.outreach.dispatch_queue import DispatchEnvelope, DispatchWorker

    ping = _make_ping(db_session)
    env = DispatchEnvelope(
        channel="whatsapp",
        to="+919999990001",
        body="Hello donor",
        idempotency_key=f"dispatch_{ping.id}",
        ping_id=str(ping.id),
        donor_id=str(ping.donor_id),
        template_key="urgent_slot_alert",
        language="en",
    )
    sqs_client.publish(env.to_dict())

    worker = DispatchWorker(session_factory=session_factory, poll_interval_seconds=0.01)
    worker._drain_once()

    assert len(mock_twilio) == 1
    db_session.refresh(ping)
    assert ping.whatsapp_sid == "fake-sid"
    assert ping.template_key == "urgent_slot_alert"
    msgs = db_session.query(WhatsAppMessage).all()
    assert len(msgs) == 1
    assert worker.stats.sent == 1


def test_worker_drains_email_envelope(
    db_session: Session, session_factory
):
    from app.integrations import sqs_client
    from app.outreach.dispatch_queue import DispatchEnvelope, DispatchWorker

    env = DispatchEnvelope(
        channel="email",
        to="caregiver@example.com",
        body="Body text",
        idempotency_key="email_test_1",
        subject="Daily digest",
        template_key="caregiver_daily_digest",
        language="en",
    )
    sqs_client.publish(env.to_dict())

    worker = DispatchWorker(session_factory=session_factory, poll_interval_seconds=0.01)
    worker._drain_once()

    rows = db_session.query(EmailMessage).all()
    assert len(rows) == 1
    assert rows[0].recipient_email == "caregiver@example.com"
    assert rows[0].is_mock is True


def test_worker_idempotency_skips_already_sent(
    db_session: Session, session_factory, mock_twilio
):
    from app.integrations import sqs_client
    from app.outreach.dispatch_queue import DispatchEnvelope, DispatchWorker

    ping = _make_ping(db_session)
    ping.whatsapp_sid = "pre-sent-SID"   # mark as already sent
    db_session.flush()

    env = DispatchEnvelope(
        channel="whatsapp", to="+919999990001", body="x",
        idempotency_key=f"dispatch_{ping.id}", ping_id=str(ping.id),
        donor_id=str(ping.donor_id),
    )
    sqs_client.publish(env.to_dict())

    worker = DispatchWorker(session_factory=session_factory, poll_interval_seconds=0.01)
    worker._drain_once()
    assert worker.stats.duplicates_skipped == 1
    assert mock_twilio == []


def test_worker_unknown_channel_drops_message(
    db_session: Session, session_factory
):
    from app.integrations import sqs_client
    from app.outreach.dispatch_queue import DispatchWorker

    sqs_client.publish({
        "channel": "carrier_pigeon", "to": "x", "body": "y",
        "idempotency_key": "weird",
    })
    worker = DispatchWorker(session_factory=session_factory, poll_interval_seconds=0.01)
    worker._drain_once()
    assert worker.stats.failed >= 1
