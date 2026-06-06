"""Phase B — follow-up API endpoint tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    Donor,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    PingResponse,
    UrgencyTier,
)


@pytest.fixture
def mock_twilio(monkeypatch):
    calls = []

    class _FakeResult:
        sid = "fake-sid"
        status = "queued"

    def _fake_send(*, to_number: str, body: str):
        calls.append({"to": to_number, "body": body})
        return _FakeResult()

    monkeypatch.setattr(
        "app.outreach.followups.twilio_client.send_whatsapp", _fake_send
    )
    monkeypatch.setattr(
        "app.outreach.followups.twilio_client.whatsapp_from", lambda: "+10000000"
    )
    return calls


def _seed_pending_ping(db: Session) -> tuple[OutreachPing, OutreachWave]:
    p = Patient(
        name="Patient API",
        age=11,
        blood_group=BloodGroup.O_POS,
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
    b = Bridge(patient_id=p.id, name="Bridge", status=BridgeStatus.ACTIVE)
    db.add(b)
    db.flush()
    w = OutreachWave(
        patient_id=p.id,
        bridge_id=b.id,
        slot_date=date(2026, 6, 9),
        tier=OutreachTier.TIER_1,
        urgency=UrgencyTier.CRITICAL,
        status=OutreachWaveStatus.ACTIVE,
        target_p_accept=0.95,
        gap_days_at_creation=2,
    )
    db.add(w)
    db.flush()
    d = Donor(
        name="Donor API",
        age=27,
        blood_group=BloodGroup.O_POS,
        rh_negative=False,
        kell_negative=False,
        phone="+919999000200",
        city="Hyderabad",
        state="Telangana",
        lat=17.40,
        lng=78.46,
        is_active=True,
        response_rate=0.6,
        registered_at=datetime(2025, 1, 1),
    )
    db.add(d)
    db.flush()
    ping = OutreachPing(
        wave_id=w.id,
        donor_id=d.id,
        response=PingResponse.PENDING,
        sent_at=datetime(2026, 6, 7, 6, 0, 0),
    )
    db.add(ping)
    db.flush()
    return ping, w


# ---------------------------------------------------------------------------
# GET /outreach/pings/{id}/follow-ups
# ---------------------------------------------------------------------------


def test_follow_ups_shape_on_fresh_ping(
    client: TestClient, db_session: Session
) -> None:
    ping, _ = _seed_pending_ping(db_session)
    r = client.get(f"/outreach/pings/{ping.id}/follow-ups")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ping_id"] == str(ping.id)
    assert body["response"] == "pending"
    assert body["nudge"]["count"] == 0
    assert body["nudge"]["last_sent_at"] is None
    assert body["reminder"]["sent_at"] is None
    assert body["thank_you"]["sent_at"] is None


def test_follow_ups_404_on_missing_ping(client: TestClient) -> None:
    import uuid as _u
    r = client.get(f"/outreach/pings/{_u.uuid4()}/follow-ups")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /outreach/pings/{id}/follow-ups/nudge — manual override
# ---------------------------------------------------------------------------


def test_manual_nudge_endpoint(
    client: TestClient, db_session: Session, mock_twilio
) -> None:
    ping, _ = _seed_pending_ping(db_session)
    r = client.post(f"/outreach/pings/{ping.id}/follow-ups/nudge")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sent"] is True
    assert body["nudge_count"] == 1
    assert body["last_nudge_at"] is not None
    assert len(mock_twilio) == 1


def test_manual_nudge_404(client: TestClient) -> None:
    import uuid as _u
    r = client.post(f"/outreach/pings/{_u.uuid4()}/follow-ups/nudge")
    assert r.status_code == 404
