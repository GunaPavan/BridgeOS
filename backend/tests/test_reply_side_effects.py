"""Tests for app.services.reply_side_effects.

Each handler is exercised against a real (test) DB session with a stubbed
Twilio dispatcher so no network calls fly.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    CooldownReason,
    Donor,
    MessageDirection,
    OutreachCooldown,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    PingResponse,
    ReplyIntent,
    UrgencyTier,
    WhatsAppMessage,
)
from app.services import reply_side_effects as side


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
        "app.services.reply_side_effects.twilio_client.send_whatsapp", _fake_send
    )
    monkeypatch.setattr(
        "app.services.reply_side_effects.twilio_client.whatsapp_from",
        lambda: "+10000000",
    )
    # The accept/decline path delegates to outreach.dispatch which uses its own
    # twilio reference (for caregiver pings etc.). Stub that too.
    try:
        monkeypatch.setattr(
            "app.outreach.dispatch.twilio_client.send_whatsapp", _fake_send
        )
        monkeypatch.setattr(
            "app.outreach.dispatch.twilio_client.whatsapp_from", lambda: "+10000000"
        )
    except AttributeError:
        pass
    return calls


def _make_donor(db: Session, *, phone: str = "+919999000300") -> Donor:
    d = Donor(
        name="Reply Donor",
        age=30,
        blood_group=BloodGroup.O_POS,
        rh_negative=False,
        kell_negative=False,
        phone=phone,
        city="Hyderabad",
        state="Telangana",
        lat=17.40,
        lng=78.46,
        is_active=True,
        response_rate=0.7,
        registered_at=datetime(2025, 1, 1),
    )
    db.add(d)
    db.flush()
    return d


def _make_wave_with_pending_ping(db: Session, donor: Donor) -> OutreachPing:
    p = Patient(
        name="Patient Side",
        age=10,
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
    b = Bridge(patient_id=p.id, name="Bridge S", status=BridgeStatus.ACTIVE)
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
    ping = OutreachPing(
        wave_id=w.id,
        donor_id=donor.id,
        response=PingResponse.PENDING,
        sent_at=datetime(2026, 6, 7, 6, 0, 0),
    )
    db.add(ping)
    db.flush()
    return ping


# ---------------------------------------------------------------------------
# on_out_of_town
# ---------------------------------------------------------------------------


def test_out_of_town_sets_7_day_cooldown_and_acks(
    db_session: Session, mock_twilio
) -> None:
    donor = _make_donor(db_session)
    res = side.on_out_of_town(db_session, donor=donor, now=datetime(2026, 6, 7))
    db_session.flush()
    assert res.handled
    assert res.cooldown_until == datetime(2026, 6, 7) + timedelta(days=7)
    cooldowns = db_session.query(OutreachCooldown).all()
    assert len(cooldowns) == 1
    assert cooldowns[0].reason == CooldownReason.OPT_OUT_TEMPORARY
    assert cooldowns[0].patient_id is None
    assert len(mock_twilio) == 1
    assert "safe travels" in mock_twilio[0]["body"].lower()


# ---------------------------------------------------------------------------
# on_medical_defer
# ---------------------------------------------------------------------------


def test_medical_defer_sets_14_day_cooldown(
    db_session: Session, mock_twilio
) -> None:
    donor = _make_donor(db_session)
    res = side.on_medical_defer(
        db_session, donor=donor, reason="fever", now=datetime(2026, 6, 7)
    )
    db_session.flush()
    assert res.handled
    assert res.cooldown_until == datetime(2026, 6, 7) + timedelta(days=14)
    cooldowns = db_session.query(OutreachCooldown).all()
    assert "fever" in (cooldowns[0].notes or "")


# ---------------------------------------------------------------------------
# on_reschedule_request
# ---------------------------------------------------------------------------


def test_reschedule_logs_preferred_date_and_acks(
    db_session: Session, mock_twilio
) -> None:
    donor = _make_donor(db_session)
    res = side.on_reschedule_request(
        db_session,
        donor=donor,
        slot_ref=None,
        preferred_date=date(2026, 6, 15),
        now=datetime(2026, 6, 7),
    )
    db_session.flush()
    assert res.handled
    assert "preferred_date=2026-06-15" in res.actions
    assert len(mock_twilio) == 1
    assert "confirm shortly" in mock_twilio[0]["body"].lower()
    # No cooldown for reschedule
    assert db_session.query(OutreachCooldown).count() == 0


# ---------------------------------------------------------------------------
# on_stop
# ---------------------------------------------------------------------------


def test_stop_opts_donor_out(db_session: Session, mock_twilio) -> None:
    donor = _make_donor(db_session)
    res = side.on_stop(db_session, donor=donor, now=datetime(2026, 6, 7))
    db_session.flush()
    assert res.handled
    cooldowns = db_session.query(OutreachCooldown).all()
    assert len(cooldowns) == 1
    assert cooldowns[0].reason == CooldownReason.OPT_OUT_TEMPORARY
    assert (cooldowns[0].expires_at - datetime(2026, 6, 7)).days >= 360


# ---------------------------------------------------------------------------
# on_unknown
# ---------------------------------------------------------------------------


def test_unknown_sends_help_hint(db_session: Session, mock_twilio) -> None:
    donor = _make_donor(db_session)
    res = side.on_unknown(db_session, donor=donor)
    db_session.flush()
    assert res.handled
    assert "sent_help_hint" in res.actions
    assert any("yes" in c["body"].lower() and "no" in c["body"].lower() for c in mock_twilio)


# ---------------------------------------------------------------------------
# on_unrelated_question
# ---------------------------------------------------------------------------


def test_unrelated_question_holds_message_when_agent_unavailable(
    db_session: Session, mock_twilio
) -> None:
    donor = _make_donor(db_session)
    # No app.agent.engine.answer_question wired → falls back to holding ack
    res = side.on_unrelated_question(
        db_session, donor=donor, text="what is the patient's blood group?"
    )
    db_session.flush()
    assert res.handled
    assert any("follow up" in c["body"].lower() for c in mock_twilio)


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------


def test_dispatch_routes_to_correct_handler(
    db_session: Session, mock_twilio
) -> None:
    donor = _make_donor(db_session)
    res = side.dispatch(
        db_session,
        intent=ReplyIntent.OUT_OF_TOWN,
        donor=donor,
        text="out of town",
    )
    db_session.flush()
    assert res.intent == ReplyIntent.OUT_OF_TOWN
    assert res.handled


# ---------------------------------------------------------------------------
# on_accept / on_decline pass-throughs (rely on existing outreach.dispatch
# helpers being correct)
# ---------------------------------------------------------------------------


def test_on_accept_returns_unhandled_when_no_pending_ping(
    db_session: Session, mock_twilio
) -> None:
    donor = _make_donor(db_session)
    res = side.on_accept(db_session, donor=donor, slot_ref=None)
    assert res.handled is False


def test_on_decline_returns_unhandled_when_no_pending_ping(
    db_session: Session, mock_twilio
) -> None:
    donor = _make_donor(db_session)
    res = side.on_decline(db_session, donor=donor, slot_ref=None)
    assert res.handled is False
