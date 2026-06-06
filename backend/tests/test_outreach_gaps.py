"""Tests for the gap-closure phase — Tier 3 broadcast template, auto-escalation,
caregiver ping on accept, cancel-acceptance reversal, coordinator overrides,
multi-unit batching, broken-bridge priority, eRaktKosh + ICMR fanout."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Bridge,
    BridgeMembership,
    BridgeStatus,
    CaregiverRelation,
    CooldownReason,
    Donor,
    Language,
    MembershipRole,
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
    cancel_outreach_acceptance,
    confirm_outreach_acceptance,
)
from app.outreach.engine import escalate_wave_to_next_tier
from app.outreach.scoring import minimal_batch
from app.services import whatsapp_templates as _tmpl


# ---------- final_ask_soft template ----------


class TestFinalAskSoft:
    def test_template_registered_in_all_8_languages(self) -> None:
        t = _tmpl.get_template("final_ask_soft")
        assert t is not None
        for lang in ("en", "hi", "te", "ta", "mr", "bn", "kn", "gu"):
            assert lang in t.bodies
            assert t.bodies[lang]

    def test_renders_with_slot_ref(self) -> None:
        out = _tmpl.render(
            "final_ask_soft",
            language="en",
            donor_first="Aakash",
            patient_name="Patient A",
            slot_date="2026-06-24",
            slot_ref="abc12345",
        )
        assert "abc12345" in out.body
        assert "Aakash" in out.body
        # Softer than urgent template — no "URGENT" prefix
        assert "URGENT" not in out.body


# ---------- minimal_batch min_size (multi-unit) ----------


class TestMultiUnitFloor:
    def _stub(self, rr: float, did: uuid.UUID = None):
        class _D:
            pass

        d = _D()
        d.id = did or uuid.uuid4()
        d.response_rate = rr
        return d

    def test_min_size_floor_overrides_p_accept_short_circuit(self) -> None:
        # Strong donor — one alone hits 0.85 — but multi-unit needs 2 floor
        cands = [self._stub(0.95), self._stub(0.9), self._stub(0.8)]
        batch = minimal_batch(
            cands,
            churn_scores={d.id: 0.0 for d in cands},
            target_p_accept=0.85,
            max_size=8,
            min_size=2,  # patient needs 2 units
        )
        assert len(batch) == 2

    def test_min_size_1_preserves_existing_behaviour(self) -> None:
        cands = [self._stub(0.95)]
        batch = minimal_batch(
            cands,
            churn_scores={d.id: 0.0 for d in cands},
            target_p_accept=0.85,
            max_size=5,
            min_size=1,
        )
        assert len(batch) == 1


# ---------- caregiver ping on accept ----------


def _wave_with_caregiver(db: Session) -> tuple[OutreachWave, Donor, Patient]:
    p = Patient(
        name="Patient w/ caregiver",
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
        last_transfusion_date=date(2026, 5, 15),
        active=True,
        caregiver_name="Sita Mother",
        caregiver_phone="+919999990001",
        caregiver_relation=CaregiverRelation.MOTHER,
    )
    db.add(p)
    db.flush()
    bridge = Bridge(patient_id=p.id, name="Bridge", status=BridgeStatus.ACTIVE)
    db.add(bridge)
    db.flush()
    wave = OutreachWave(
        patient_id=p.id,
        bridge_id=bridge.id,
        slot_date=date(2026, 6, 8),
        tier=OutreachTier.TIER_1,
        urgency=UrgencyTier.CRITICAL,
        status=OutreachWaveStatus.ACTIVE,
        target_p_accept=0.95,
        gap_days_at_creation=2,
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    db.add(wave)
    db.flush()
    d = Donor(
        name="Aakash D",
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
    )
    db.add(d)
    db.flush()
    db.add(
        OutreachPing(
            wave_id=wave.id,
            donor_id=d.id,
            response=PingResponse.PENDING,
            sent_at=datetime.utcnow(),
        )
    )
    db.flush()
    return wave, d, p


class TestCaregiverPingOnAccept:
    def test_accept_fires_caregiver_transfusion_confirmed_message(
        self, db_session: Session
    ) -> None:
        wave, donor, patient = _wave_with_caregiver(db_session)
        with patch("app.outreach.dispatch.twilio_client") as mock:
            mock.send_whatsapp.return_value = MagicMock(sid="SM-care", status="queued")
            mock.whatsapp_from.return_value = "whatsapp:+14155238886"
            confirm_outreach_acceptance(db_session, donor_id=donor.id)
        msgs = db_session.execute(
            select(WhatsAppMessage).where(
                WhatsAppMessage.template_key == "transfusion_confirmed_caregiver"
            )
        ).scalars().all()
        assert len(msgs) == 1
        assert msgs[0].to_number == patient.caregiver_phone
        assert donor.name in msgs[0].body
        assert patient.name in msgs[0].body

    def test_no_caregiver_phone_does_not_break_accept(self, db_session: Session) -> None:
        wave, donor, patient = _wave_with_caregiver(db_session)
        patient.caregiver_phone = None
        db_session.flush()
        with patch("app.outreach.dispatch.twilio_client") as mock:
            mock.send_whatsapp.return_value = MagicMock(sid="SM-x", status="queued")
            mock.whatsapp_from.return_value = "whatsapp:+14155238886"
            # Should not raise
            confirm_outreach_acceptance(db_session, donor_id=donor.id)
        # And no caregiver message exists
        msgs = db_session.execute(
            select(WhatsAppMessage).where(
                WhatsAppMessage.template_key == "transfusion_confirmed_caregiver"
            )
        ).scalars().all()
        assert len(msgs) == 0


# ---------- cancel_outreach_acceptance ----------


class TestCancelAcceptance:
    def test_reverses_wave_status_and_ping_and_cooldowns(
        self, db_session: Session
    ) -> None:
        wave, donor, _ = _wave_with_caregiver(db_session)
        with patch("app.outreach.dispatch.twilio_client") as mock:
            mock.send_whatsapp.return_value = MagicMock(sid="SM-x", status="queued")
            mock.whatsapp_from.return_value = "whatsapp:+14155238886"
            confirm_outreach_acceptance(db_session, donor_id=donor.id)

        db_session.refresh(wave)
        assert wave.status == OutreachWaveStatus.ACCEPTED

        # Now reverse it
        reversed_wave = cancel_outreach_acceptance(db_session, donor_id=donor.id)
        assert reversed_wave is not None
        assert reversed_wave.id == wave.id

        db_session.refresh(wave)
        # Wave reopened
        assert wave.status == OutreachWaveStatus.ACTIVE
        assert wave.resolved_by_donor_id is None
        # Ping flipped DECLINED
        ping = wave.pings[0]
        assert ping.response == PingResponse.DECLINED
        # 90-day clinical cooldown removed, 30-day per-patient cooldown added
        cds = db_session.execute(select(OutreachCooldown)).scalars().all()
        kinds = {cd.reason for cd in cds}
        assert CooldownReason.RECENT_DONATION not in kinds  # gone
        assert CooldownReason.DECLINED in kinds  # added

    def test_no_accepted_wave_returns_none(self, db_session: Session) -> None:
        result = cancel_outreach_acceptance(db_session, donor_id=uuid.uuid4())
        assert result is None


# ---------- escalate_wave_to_next_tier ----------


class TestEscalateNextTier:
    def _make_wave(self, db: Session, *, tier: OutreachTier) -> tuple[OutreachWave, Donor, Patient]:
        wave, donor, patient = _wave_with_caregiver(db)
        wave.tier = tier
        wave.status = OutreachWaveStatus.EXPIRED
        # Need patient gap_days inside horizon so escalate doesn't return None
        patient.last_transfusion_date = date.today() - timedelta(days=20)
        patient.transfusion_cadence_days = 21
        db.flush()
        return wave, donor, patient

    def test_tier1_escalates_to_tier2_with_different_donors(
        self, db_session: Session
    ) -> None:
        wave, donor, patient = self._make_wave(db_session, tier=OutreachTier.TIER_1)
        # Add 4 more donors so Tier 2 has fresh candidates
        for i in range(4):
            db_session.add(
                Donor(
                    name=f"Extra {i}",
                    age=29,
                    blood_group=BloodGroup.O_POS,
                    rh_negative=False,
                    kell_negative=False,
                    phone=f"+91999900099{i}",
                    city="Hyderabad",
                    state="Telangana",
                    lat=17.40 + 0.005 * i,
                    lng=78.46,
                    is_active=True,
                    response_rate=0.7,
                    registered_at=datetime(2025, 1, 1),
                )
            )
        db_session.flush()

        new_wave = escalate_wave_to_next_tier(
            db_session, expired_wave=wave, today=date.today()
        )
        assert new_wave is not None
        assert new_wave.tier == OutreachTier.TIER_2
        # New wave excludes the donor who was in the expired Tier-1 wave
        new_donor_ids = [p.donor_id for p in new_wave.pings]
        assert donor.id not in new_donor_ids

    def test_tier2_escalates_directly_to_tier3(
        self, db_session: Session
    ) -> None:
        """Manual Call Queue was removed — Tier 2 escalates straight to Tier 3
        (full-pool soft-tone broadcast) instead of dropping into a human-in-
        the-loop queue."""
        wave, donor, patient = self._make_wave(
            db_session, tier=OutreachTier.TIER_2
        )
        # Force the wave to actually need re-escalation (no donor responded)
        new_wave = escalate_wave_to_next_tier(
            db_session, expired_wave=wave, today=date.today()
        )
        assert new_wave is not None
        assert new_wave.tier == OutreachTier.TIER_3

    def test_tier3_to_external_returns_none(self, db_session: Session) -> None:
        wave, _, _ = self._make_wave(db_session, tier=OutreachTier.TIER_3)
        new_wave = escalate_wave_to_next_tier(
            db_session, expired_wave=wave, today=date.today()
        )
        # External tier doesn't create a wave — coordinator alert path
        assert new_wave is None


# ---------- coordinator overrides via API ----------


def _seed_basic_wave(db: Session) -> tuple[OutreachWave, list[Donor]]:
    p = Patient(
        name="P-overr",
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
        slot_date=date(2026, 6, 8),
        tier=OutreachTier.TIER_1,
        urgency=UrgencyTier.CRITICAL,
        status=OutreachWaveStatus.ACTIVE,
        target_p_accept=0.95,
        gap_days_at_creation=2,
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    db.add(wave)
    db.flush()
    donors = []
    for i in range(3):
        d = Donor(
            name=f"D-{i}",
            age=30,
            blood_group=BloodGroup.O_POS,
            rh_negative=False,
            kell_negative=False,
            phone=f"+9199990000{i:02d}",
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
        donors.append(d)
        if i < 2:
            db.add(
                OutreachPing(
                    wave_id=wave.id,
                    donor_id=d.id,
                    response=PingResponse.PENDING,
                    sent_at=datetime.utcnow(),
                )
            )
    db.flush()
    db.commit()
    return wave, donors


class TestForceIncludeExclude:
    def test_force_include_adds_a_new_ping(self, client, db_session: Session) -> None:
        wave, donors = _seed_basic_wave(db_session)
        # Donor 3 isn't in the wave yet
        extra = donors[2]
        r = client.post(
            f"/outreach/waves/{wave.id}/force-include?donor_id={extra.id}"
        ).json()
        assert "ping_id" in r
        db_session.refresh(wave)
        donor_ids = [p.donor_id for p in wave.pings]
        assert extra.id in donor_ids

    def test_force_include_409_on_duplicate(self, client, db_session: Session) -> None:
        wave, donors = _seed_basic_wave(db_session)
        already = donors[0]  # already pinged
        r = client.post(
            f"/outreach/waves/{wave.id}/force-include?donor_id={already.id}"
        )
        assert r.status_code == 409

    def test_force_exclude_cancels_a_pending_ping(self, client, db_session: Session) -> None:
        wave, donors = _seed_basic_wave(db_session)
        target = donors[0]
        r = client.post(
            f"/outreach/waves/{wave.id}/force-exclude?donor_id={target.id}"
        )
        assert r.status_code == 200
        ping = next(p for p in wave.pings if p.donor_id == target.id)
        db_session.refresh(ping)
        assert ping.response == PingResponse.CANCELLED


# ---------- eRaktKosh + ICMR parallel fetch on emergency ----------


class TestEmergencyExternalFanout:
    def test_eraktkosh_and_icmr_lists_populated_on_trigger(
        self, db_session: Session
    ) -> None:
        from app.outreach.emergency import trigger_emergency

        p = Patient(
            name="EM patient",
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
            last_transfusion_date=date(2026, 5, 15),
            active=True,
        )
        db_session.add(p)
        db_session.flush()

        now = datetime(2026, 6, 6, 12, 0, 0)
        result = trigger_emergency(
            db_session,
            patient_id=p.id,
            coordinator_name="Coord",
            transfusion_deadline_at=now + timedelta(hours=4),
            justification="Severe",
            now=now,
        )
        # eRaktKosh + ICMR fixtures live in app.integrations — they shouldn't be empty
        assert isinstance(result.eraktkosh_banks, list)
        assert isinstance(result.icmr_rare_donors, list)
        # Both should return SOMETHING for Hyderabad B+ in our seeded mocks
        assert len(result.eraktkosh_banks) >= 1
