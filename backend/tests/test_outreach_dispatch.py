"""Tests for Phase C — WhatsApp dispatch + acceptance close + decline + expiry."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time as dt_time, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Bridge,
    BridgeMembership,
    BridgeStatus,
    CooldownReason,
    Donor,
    Language,
    MembershipStatus,
    OutreachCooldown,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    PingResponse,
    UrgencyTier,
    WhatsAppMessage,
)
from app.outreach.dispatch import (
    confirm_outreach_acceptance,
    dispatch_wave,
    expire_pending_pings,
    is_quiet_hours,
    make_slot_ref,
    parse_slot_ref,
    record_outreach_decline,
)


# ---------- builders ----------


def _build_wave_with_pings(
    db: Session, *, n_donors: int = 3, language: str = "en"
) -> tuple[OutreachWave, list[Donor], Patient]:
    p = Patient(
        name="Test Patient",
        age=12,
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
    bridge = Bridge(patient_id=p.id, name="Bridge", status=BridgeStatus.ACTIVE)
    db.add(bridge)
    db.flush()
    wave = OutreachWave(
        patient_id=p.id,
        bridge_id=bridge.id,
        slot_date=date(2026, 6, 7),
        tier=OutreachTier.TIER_1,
        urgency=UrgencyTier.CRITICAL,
        status=OutreachWaveStatus.ACTIVE,
        target_p_accept=0.95,
        gap_days_at_creation=1,
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    db.add(wave)
    db.flush()
    donors = []
    for i in range(n_donors):
        d = Donor(
            name=f"Donor {i}",
            age=30,
            blood_group=BloodGroup.O_POS,
            rh_negative=False,
            kell_negative=False,
            phone=f"+9199999000{i:02d}",
            city="Hyderabad",
            state="Telangana",
            lat=17.40,
            lng=78.46,
            is_active=True,
            response_rate=0.7,
            preferred_language=Language(language) if language else Language.ENGLISH,
            registered_at=datetime(2025, 1, 1),
        )
        db.add(d)
        db.flush()
        donors.append(d)
        ping = OutreachPing(
            wave_id=wave.id,
            donor_id=d.id,
            response=PingResponse.PENDING,
            sent_at=datetime.utcnow(),
            expires_at=wave.expires_at,
        )
        db.add(ping)
    db.flush()
    return wave, donors, p


# ---------- pure-helper tests ----------


class TestQuietHours:
    def test_2330_ist_is_quiet(self) -> None:
        # 23:30 IST = 18:00 UTC (IST = UTC+5:30)
        utc_at_2330_ist = datetime(2026, 6, 6, 18, 0, 0)
        assert is_quiet_hours(utc_at_2330_ist) is True

    def test_0500_ist_is_quiet(self) -> None:
        # 05:00 IST = 23:30 UTC prev day
        utc_at_0500_ist = datetime(2026, 6, 5, 23, 30, 0)
        assert is_quiet_hours(utc_at_0500_ist) is True

    def test_1000_ist_is_not_quiet(self) -> None:
        utc_at_1000_ist = datetime(2026, 6, 6, 4, 30, 0)
        assert is_quiet_hours(utc_at_1000_ist) is False

    def test_1500_ist_is_not_quiet(self) -> None:
        utc_at_1500_ist = datetime(2026, 6, 6, 9, 30, 0)
        assert is_quiet_hours(utc_at_1500_ist) is False


class TestSlotRefRoundtrip:
    def test_make_slot_ref_is_8_hex_chars(self) -> None:
        ref = make_slot_ref(uuid.UUID("abcdef12-3456-7890-1234-567890abcdef"))
        assert ref == "abcdef12"
        assert len(ref) == 8

    def test_parse_extracts_ref_from_body(self) -> None:
        body = "YES — count me in! (ref abcdef12)"
        assert parse_slot_ref(body) == "abcdef12"

    def test_parse_is_case_insensitive(self) -> None:
        assert parse_slot_ref("Ref ABCDEF12 ok") == "abcdef12"

    def test_parse_missing_returns_none(self) -> None:
        assert parse_slot_ref("just a yes") is None

    def test_parse_empty_safe(self) -> None:
        assert parse_slot_ref("") is None
        assert parse_slot_ref(None) is None  # type: ignore[arg-type]


# ---------- dispatch_wave ----------


class TestDispatchWave:
    @pytest.fixture(autouse=True)
    def _inline_dispatch(self, monkeypatch):
        """These tests assert dispatch_wave's SYNCHRONOUS contract — pings get
        stamped + WhatsAppMessage rows appear inside the call. Phase E3
        moved the default path through SQS, which is asynchronous. Force the
        legacy inline path here so the contract these tests assert still
        holds. The async path has its own coverage in test_dispatch_queue_*.
        """
        monkeypatch.setenv("BRIDGE_OS_DISPATCH_INLINE", "1")

    def _stub_twilio(self):
        """Stub send_whatsapp + whatsapp_from so no real network."""
        return patch("app.outreach.dispatch.twilio_client")

    def test_sends_one_message_per_pending_ping(self, db_session: Session) -> None:
        wave, donors, p = _build_wave_with_pings(db_session)
        # Force non-quiet
        with self._stub_twilio() as mock:
            mock.send_whatsapp.return_value = MagicMock(sid="SM123", status="queued")
            mock.whatsapp_from.return_value = "whatsapp:+14155238886"
            now = datetime(2026, 6, 6, 9, 0, 0)  # 14:30 IST — definitely not quiet
            summary = dispatch_wave(wave, db=db_session, now=now)
        assert summary.pings_sent == 3
        assert summary.pings_suppressed_quiet_hours == 0
        # All pings now have a SID
        db_session.refresh(wave)
        assert all(p.whatsapp_sid == "SM123" for p in wave.pings)
        # Donor last_contacted_date updated for each
        for d in donors:
            db_session.refresh(d)
            assert d.last_contacted_date == now.date()
            assert d.total_calls == 1

    def test_quiet_hours_suppress_unless_override(self, db_session: Session) -> None:
        wave, donors, _ = _build_wave_with_pings(db_session)
        with self._stub_twilio() as mock:
            mock.send_whatsapp.return_value = MagicMock(sid="SM-x", status="queued")
            mock.whatsapp_from.return_value = "whatsapp:+14155238886"
            quiet_utc = datetime(2026, 6, 6, 18, 30, 0)  # ~ midnight IST
            summary = dispatch_wave(wave, db=db_session, now=quiet_utc)
        assert summary.pings_sent == 0
        assert summary.pings_suppressed_quiet_hours == 3
        # No Twilio sends should have happened
        assert mock.send_whatsapp.call_count == 0

    def test_override_quiet_hours_sends_anyway(self, db_session: Session) -> None:
        wave, donors, _ = _build_wave_with_pings(db_session)
        with self._stub_twilio() as mock:
            mock.send_whatsapp.return_value = MagicMock(sid="SM-x", status="queued")
            mock.whatsapp_from.return_value = "whatsapp:+14155238886"
            quiet_utc = datetime(2026, 6, 6, 18, 30, 0)
            summary = dispatch_wave(
                wave, db=db_session, now=quiet_utc, override_quiet_hours=True
            )
        assert summary.pings_sent == 3
        assert summary.pings_suppressed_quiet_hours == 0

    def test_dispatched_pings_mirror_to_whatsapp_messages(self, db_session: Session) -> None:
        wave, donors, _ = _build_wave_with_pings(db_session)
        with self._stub_twilio() as mock:
            mock.send_whatsapp.return_value = MagicMock(sid="SM-mirror", status="queued")
            mock.whatsapp_from.return_value = "whatsapp:+14155238886"
            dispatch_wave(wave, db=db_session, now=datetime(2026, 6, 6, 9, 0, 0))
        messages = db_session.execute(select(WhatsAppMessage)).scalars().all()
        assert len(messages) == 3
        assert all(m.template_key == "urgent_slot_alert" for m in messages)
        assert all("Apollo" not in m.body for m in messages)  # template doesn't mention hospital
        assert all("ref " in m.body for m in messages)        # slot_ref token included


# ---------- confirm acceptance ----------


class TestConfirmAcceptance:
    def test_yes_closes_wave_and_cancels_siblings(self, db_session: Session) -> None:
        wave, donors, p = _build_wave_with_pings(db_session, n_donors=4)
        # Pretend they were already sent
        for ping in wave.pings:
            ping.whatsapp_sid = "SM-x"
        db_session.flush()

        winner_donor = donors[1]
        accepted_wave = confirm_outreach_acceptance(
            db_session, donor_id=winner_donor.id
        )
        assert accepted_wave is not None
        assert accepted_wave.id == wave.id
        # Wave flipped
        db_session.refresh(wave)
        assert wave.status == OutreachWaveStatus.ACCEPTED
        assert wave.resolved_by_donor_id == winner_donor.id
        # Winning ping is ACCEPTED, siblings CANCELLED
        responses = {p.donor_id: p.response for p in wave.pings}
        assert responses[winner_donor.id] == PingResponse.ACCEPTED
        sibling_responses = [
            r for did, r in responses.items() if did != winner_donor.id
        ]
        assert all(r == PingResponse.CANCELLED for r in sibling_responses)

    def test_yes_creates_90day_clinical_cooldown(self, db_session: Session) -> None:
        wave, donors, _ = _build_wave_with_pings(db_session, n_donors=2)
        confirm_outreach_acceptance(db_session, donor_id=donors[0].id)
        cooldowns = (
            db_session.execute(
                select(OutreachCooldown).where(
                    OutreachCooldown.donor_id == donors[0].id
                )
            )
            .scalars()
            .all()
        )
        assert len(cooldowns) == 1
        assert cooldowns[0].reason == CooldownReason.RECENT_DONATION
        # Cooldown is global (patient_id=None) because deferral is clinical
        assert cooldowns[0].patient_id is None
        # ~90 days out
        diff = cooldowns[0].expires_at - datetime.utcnow()
        assert timedelta(days=89) <= diff <= timedelta(days=91)

    def test_yes_with_explicit_slot_ref_targets_right_ping(
        self, db_session: Session
    ) -> None:
        wave, donors, _ = _build_wave_with_pings(db_session, n_donors=3)
        ping_for_donor_2 = next(p for p in wave.pings if p.donor_id == donors[2].id)
        slot_ref = make_slot_ref(ping_for_donor_2.id)
        confirm_outreach_acceptance(
            db_session, donor_id=donors[2].id, slot_ref=slot_ref
        )
        db_session.refresh(ping_for_donor_2)
        assert ping_for_donor_2.response == PingResponse.ACCEPTED

    def test_yes_with_no_pending_ping_returns_none(self, db_session: Session) -> None:
        result = confirm_outreach_acceptance(db_session, donor_id=uuid.uuid4())
        assert result is None

    def test_yes_promotes_donor_to_active_bridge_membership(
        self, db_session: Session
    ) -> None:
        wave, donors, _ = _build_wave_with_pings(db_session, n_donors=2)
        confirm_outreach_acceptance(db_session, donor_id=donors[0].id)
        memberships = (
            db_session.execute(
                select(BridgeMembership).where(
                    BridgeMembership.donor_id == donors[0].id
                )
            )
            .scalars()
            .all()
        )
        assert len(memberships) == 1
        assert memberships[0].status == MembershipStatus.ACTIVE


# ---------- decline ----------


class TestDecline:
    def test_no_creates_30day_per_patient_cooldown(self, db_session: Session) -> None:
        wave, donors, p = _build_wave_with_pings(db_session)
        record_outreach_decline(db_session, donor_id=donors[0].id)
        cooldowns = (
            db_session.execute(
                select(OutreachCooldown).where(
                    OutreachCooldown.donor_id == donors[0].id
                )
            )
            .scalars()
            .all()
        )
        assert len(cooldowns) == 1
        assert cooldowns[0].reason == CooldownReason.DECLINED
        # Per-patient cooldown — donor remains free for other patients
        assert cooldowns[0].patient_id == p.id
        diff = cooldowns[0].expires_at - datetime.utcnow()
        assert timedelta(days=29) <= diff <= timedelta(days=31)

    def test_no_marks_only_one_ping_other_pings_unchanged(self, db_session: Session) -> None:
        wave, donors, _ = _build_wave_with_pings(db_session, n_donors=3)
        record_outreach_decline(db_session, donor_id=donors[0].id)
        responses = {p.donor_id: p.response for p in wave.pings}
        assert responses[donors[0].id] == PingResponse.DECLINED
        # The wave is NOT marked accepted/cancelled; other pings still PENDING
        db_session.refresh(wave)
        assert wave.status == OutreachWaveStatus.ACTIVE
        assert responses[donors[1].id] == PingResponse.PENDING
        assert responses[donors[2].id] == PingResponse.PENDING


# ---------- expiry ----------


class TestExpire:
    def test_expire_flips_pending_pings_to_no_reply(self, db_session: Session) -> None:
        wave, donors, _ = _build_wave_with_pings(db_session, n_donors=3)
        n_flipped = expire_pending_pings(db_session, wave_id=wave.id)
        assert n_flipped == 3
        db_session.refresh(wave)
        assert all(p.response == PingResponse.NO_REPLY for p in wave.pings)

    def test_expire_creates_7day_cooldowns(self, db_session: Session) -> None:
        wave, donors, _ = _build_wave_with_pings(db_session, n_donors=2)
        expire_pending_pings(db_session, wave_id=wave.id)
        cooldowns = db_session.execute(select(OutreachCooldown)).scalars().all()
        assert len(cooldowns) == 2
        for cd in cooldowns:
            assert cd.reason == CooldownReason.NO_REPLY
            # 7-day global cooldown
            diff = cd.expires_at - datetime.utcnow()
            assert timedelta(days=6) <= diff <= timedelta(days=8)
            assert cd.patient_id is None  # global

    def test_expire_skips_already_resolved_pings(self, db_session: Session) -> None:
        wave, donors, _ = _build_wave_with_pings(db_session, n_donors=3)
        # First donor accepted; other two are pending
        wave.pings[0].response = PingResponse.ACCEPTED
        db_session.flush()
        n = expire_pending_pings(db_session, wave_id=wave.id)
        assert n == 2  # only the still-PENDING ones
