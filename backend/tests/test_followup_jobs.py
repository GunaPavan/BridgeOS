"""Phase B — automated follow-up job tests.

Covers:
  - auto_pending_nudge: PENDING > 4h triggers, idempotent across reruns,
    quiet hours defer, cap honoured
  - auto_pre_donation_reminder: ACCEPTED + slot=tomorrow triggers once
  - auto_post_donation_thank_you: ACCEPTED + slot <= yesterday triggers once
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
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
from app.scheduler.jobs import (
    auto_pending_nudge,
    auto_post_donation_thank_you,
    auto_pre_donation_reminder,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _seed_wave_with_ping(
    db: Session,
    *,
    slot_date: date,
    ping_response: PingResponse,
    sent_at: datetime,
    reminder_sent_at: datetime | None = None,
    thank_you_sent_at: datetime | None = None,
    last_nudge_at: datetime | None = None,
    nudge_count: int = 0,
) -> tuple[OutreachPing, OutreachWave, Donor, Patient]:
    p = Patient(
        name="Patient F",
        age=10,
        blood_group=BloodGroup.B_POS,
        rh_negative=False,
        kell_negative=False,
        city="Hyderabad",
        state="Telangana",
        lat=17.39,
        lng=78.46,
        hospital="Apollo Hospitals",
        transfusion_cadence_days=21,
        last_transfusion_date=date(2026, 5, 15),
        active=True,
    )
    db.add(p)
    db.flush()
    bridge = Bridge(patient_id=p.id, name="Bridge F", status=BridgeStatus.ACTIVE)
    db.add(bridge)
    db.flush()
    wave = OutreachWave(
        patient_id=p.id,
        bridge_id=bridge.id,
        slot_date=slot_date,
        tier=OutreachTier.TIER_1,
        urgency=UrgencyTier.CRITICAL,
        status=OutreachWaveStatus.ACTIVE,
        target_p_accept=0.95,
        gap_days_at_creation=2,
    )
    db.add(wave)
    db.flush()
    d = Donor(
        name="Donor F",
        age=30,
        blood_group=BloodGroup.O_POS,
        rh_negative=False,
        kell_negative=False,
        phone="+919999000100",
        city="Hyderabad",
        state="Telangana",
        lat=17.40,
        lng=78.46,
        is_active=True,
        response_rate=0.7,
        registered_at=datetime(2025, 1, 1),
        last_donation_date=date(2026, 5, 1),
    )
    db.add(d)
    db.flush()
    ping = OutreachPing(
        wave_id=wave.id,
        donor_id=d.id,
        response=ping_response,
        sent_at=sent_at,
        nudge_count=nudge_count,
        last_nudge_at=last_nudge_at,
        reminder_sent_at=reminder_sent_at,
        thank_you_sent_at=thank_you_sent_at,
    )
    db.add(ping)
    db.flush()
    return ping, wave, d, p


@pytest.fixture
def mock_twilio(monkeypatch):
    """Stub the Twilio dispatcher so no real WhatsApp calls fly."""
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


@pytest.fixture
def not_quiet(monkeypatch):
    """Force the quiet-hours check to return False so jobs actually run."""
    monkeypatch.setattr("app.scheduler.jobs._is_quiet_hours_now", lambda now: False)


@pytest.fixture
def is_quiet(monkeypatch):
    monkeypatch.setattr("app.scheduler.jobs._is_quiet_hours_now", lambda now: True)


# ---------------------------------------------------------------------------
# auto_pending_nudge
# ---------------------------------------------------------------------------


class TestPendingNudge:
    def test_sends_when_pending_past_threshold(
        self, db_session: Session, mock_twilio, not_quiet
    ) -> None:
        now = datetime(2026, 6, 7, 10, 0, 0)
        ping, *_ = _seed_wave_with_ping(
            db_session,
            slot_date=date(2026, 6, 9),
            ping_response=PingResponse.PENDING,
            sent_at=now - timedelta(hours=5),
        )
        result = auto_pending_nudge(db=db_session, now=now)
        assert result.items_processed == 1
        assert len(mock_twilio) == 1
        db_session.refresh(ping)
        assert ping.nudge_count == 1
        assert ping.last_nudge_at == now

    def test_skips_when_recently_sent(
        self, db_session: Session, mock_twilio, not_quiet
    ) -> None:
        now = datetime(2026, 6, 7, 10, 0, 0)
        ping, *_ = _seed_wave_with_ping(
            db_session,
            slot_date=date(2026, 6, 9),
            ping_response=PingResponse.PENDING,
            sent_at=now - timedelta(hours=1),  # too fresh
        )
        result = auto_pending_nudge(db=db_session, now=now)
        assert result.items_processed == 0
        assert mock_twilio == []
        db_session.refresh(ping)
        assert ping.nudge_count == 0

    def test_skips_when_already_nudged_recently(
        self, db_session: Session, mock_twilio, not_quiet
    ) -> None:
        now = datetime(2026, 6, 7, 10, 0, 0)
        ping, *_ = _seed_wave_with_ping(
            db_session,
            slot_date=date(2026, 6, 9),
            ping_response=PingResponse.PENDING,
            sent_at=now - timedelta(hours=10),
            last_nudge_at=now - timedelta(hours=2),  # < 12h ago
            nudge_count=1,
        )
        result = auto_pending_nudge(db=db_session, now=now)
        assert result.items_processed == 0
        db_session.refresh(ping)
        assert ping.nudge_count == 1

    def test_cap_at_max_nudges(
        self, db_session: Session, mock_twilio, not_quiet
    ) -> None:
        now = datetime(2026, 6, 7, 10, 0, 0)
        ping, *_ = _seed_wave_with_ping(
            db_session,
            slot_date=date(2026, 6, 9),
            ping_response=PingResponse.PENDING,
            sent_at=now - timedelta(days=2),
            last_nudge_at=now - timedelta(hours=24),
            nudge_count=2,  # already at cap
        )
        result = auto_pending_nudge(db=db_session, now=now)
        assert result.items_processed == 0

    def test_idempotent_back_to_back(
        self, db_session: Session, mock_twilio, not_quiet
    ) -> None:
        now = datetime(2026, 6, 7, 10, 0, 0)
        _seed_wave_with_ping(
            db_session,
            slot_date=date(2026, 6, 9),
            ping_response=PingResponse.PENDING,
            sent_at=now - timedelta(hours=5),
        )
        r1 = auto_pending_nudge(db=db_session, now=now)
        # Run immediately again — last_nudge_at < 12h so no resend
        r2 = auto_pending_nudge(db=db_session, now=now + timedelta(minutes=5))
        assert r1.items_processed == 1
        assert r2.items_processed == 0
        assert len(mock_twilio) == 1

    def test_quiet_hours_defers(
        self, db_session: Session, mock_twilio, is_quiet
    ) -> None:
        now = datetime(2026, 6, 7, 23, 0, 0)
        _seed_wave_with_ping(
            db_session,
            slot_date=date(2026, 6, 9),
            ping_response=PingResponse.PENDING,
            sent_at=now - timedelta(hours=10),
        )
        result = auto_pending_nudge(db=db_session, now=now)
        assert result.skipped_reason == "quiet_hours"
        assert mock_twilio == []


# ---------------------------------------------------------------------------
# auto_pre_donation_reminder
# ---------------------------------------------------------------------------


class TestPreDonationReminder:
    def test_sends_when_accepted_and_slot_is_tomorrow(
        self, db_session: Session, mock_twilio, not_quiet
    ) -> None:
        now = datetime(2026, 6, 7, 10, 0, 0)
        tomorrow = now.date() + timedelta(days=1)
        ping, *_ = _seed_wave_with_ping(
            db_session,
            slot_date=tomorrow,
            ping_response=PingResponse.ACCEPTED,
            sent_at=now - timedelta(days=2),
        )
        result = auto_pre_donation_reminder(db=db_session, now=now)
        assert result.items_processed == 1
        db_session.refresh(ping)
        assert ping.reminder_sent_at == now

    def test_skips_when_not_tomorrow(
        self, db_session: Session, mock_twilio, not_quiet
    ) -> None:
        now = datetime(2026, 6, 7, 10, 0, 0)
        _seed_wave_with_ping(
            db_session,
            slot_date=now.date() + timedelta(days=3),
            ping_response=PingResponse.ACCEPTED,
            sent_at=now - timedelta(days=2),
        )
        result = auto_pre_donation_reminder(db=db_session, now=now)
        assert result.items_processed == 0

    def test_skips_when_response_not_accepted(
        self, db_session: Session, mock_twilio, not_quiet
    ) -> None:
        now = datetime(2026, 6, 7, 10, 0, 0)
        _seed_wave_with_ping(
            db_session,
            slot_date=now.date() + timedelta(days=1),
            ping_response=PingResponse.PENDING,
            sent_at=now - timedelta(days=2),
        )
        result = auto_pre_donation_reminder(db=db_session, now=now)
        assert result.items_processed == 0

    def test_idempotent(
        self, db_session: Session, mock_twilio, not_quiet
    ) -> None:
        now = datetime(2026, 6, 7, 10, 0, 0)
        ping, *_ = _seed_wave_with_ping(
            db_session,
            slot_date=now.date() + timedelta(days=1),
            ping_response=PingResponse.ACCEPTED,
            sent_at=now - timedelta(days=2),
        )
        r1 = auto_pre_donation_reminder(db=db_session, now=now)
        r2 = auto_pre_donation_reminder(db=db_session, now=now + timedelta(minutes=5))
        assert r1.items_processed == 1
        assert r2.items_processed == 0
        assert len(mock_twilio) == 1


# ---------------------------------------------------------------------------
# auto_post_donation_thank_you
# ---------------------------------------------------------------------------


class TestPostDonationThankYou:
    def test_sends_when_donation_was_yesterday(
        self, db_session: Session, mock_twilio, not_quiet
    ) -> None:
        now = datetime(2026, 6, 7, 14, 0, 0)
        yesterday = now.date() - timedelta(days=1)
        ping, *_ = _seed_wave_with_ping(
            db_session,
            slot_date=yesterday,
            ping_response=PingResponse.ACCEPTED,
            sent_at=now - timedelta(days=3),
        )
        result = auto_post_donation_thank_you(db=db_session, now=now)
        assert result.items_processed == 1
        db_session.refresh(ping)
        assert ping.thank_you_sent_at == now

    def test_skips_when_slot_is_future(
        self, db_session: Session, mock_twilio, not_quiet
    ) -> None:
        now = datetime(2026, 6, 7, 14, 0, 0)
        _seed_wave_with_ping(
            db_session,
            slot_date=now.date() + timedelta(days=1),
            ping_response=PingResponse.ACCEPTED,
            sent_at=now - timedelta(days=2),
        )
        result = auto_post_donation_thank_you(db=db_session, now=now)
        assert result.items_processed == 0

    def test_idempotent(
        self, db_session: Session, mock_twilio, not_quiet
    ) -> None:
        now = datetime(2026, 6, 7, 14, 0, 0)
        ping, *_ = _seed_wave_with_ping(
            db_session,
            slot_date=now.date() - timedelta(days=1),
            ping_response=PingResponse.ACCEPTED,
            sent_at=now - timedelta(days=3),
        )
        r1 = auto_post_donation_thank_you(db=db_session, now=now)
        r2 = auto_post_donation_thank_you(db=db_session, now=now + timedelta(hours=1))
        assert r1.items_processed == 1
        assert r2.items_processed == 0
        assert len(mock_twilio) == 1
