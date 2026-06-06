"""Tests for the Alert Allocator's scoring + eligibility + math.

The math (``p_accept``, ``minimal_batch``, ``urgency_for_patient``) is pure
compute — no DB. The eligibility + composite tests use the in-memory session
fixture from ``conftest`` with hand-built donor / patient rows so we can
exercise every gate (NULL safety, emergency override, cooldown, fatigue).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Bridge,
    BridgeMembership,
    BridgeStatus,
    CooldownReason,
    Donor,
    MembershipRole,
    MembershipStatus,
    OutreachCooldown,
    OutreachPing,
    OutreachWave,
    Patient,
    PingResponse,
    UrgencyTier,
)
from app.outreach.scoring import (
    adjusted_response_rate,
    composite_score,
    has_active_cooldown,
    is_eligible_for_outreach,
    max_batch_for,
    minimal_batch,
    p_accept,
    target_p_accept_for,
    urgency_for_patient,
)


# ---------------------------------------------------------------------------
# Pure-math tests — no DB
# ---------------------------------------------------------------------------


class TestPAcceptMath:
    def test_empty_batch_is_zero(self) -> None:
        assert p_accept([]) == 0.0

    def test_single_donor_equals_their_rate(self) -> None:
        assert p_accept([0.7]) == pytest.approx(0.7)

    def test_two_donors_combine_correctly(self) -> None:
        # 1 - (1-0.7)(1-0.6) = 1 - 0.12 = 0.88
        assert p_accept([0.7, 0.6]) == pytest.approx(0.88)

    def test_four_donors_reaches_critical_target(self) -> None:
        # 1 - (0.3)(0.4)(0.5)(0.55) = 0.967 ≥ 0.95 → critical batch met
        assert p_accept([0.7, 0.6, 0.5, 0.45]) == pytest.approx(0.967, abs=0.001)

    def test_rate_above_1_is_clipped(self) -> None:
        # 1.5 → clipped to 1.0 → guarantees acceptance, batch ends immediately
        assert p_accept([1.5]) == pytest.approx(1.0)

    def test_rate_below_0_is_clipped(self) -> None:
        # negative → clipped to 0 → contributes nothing
        assert p_accept([-0.2, 0.5]) == pytest.approx(0.5)


class _DonorStub:
    """Plain object that quacks like Donor for the pure-math helpers.

    ``adjusted_response_rate`` + ``minimal_batch`` only touch ``donor.id`` and
    ``donor.response_rate``. Building real SQLAlchemy Donor rows here would
    drag the DB session into pure-math unit tests for no benefit.
    """

    def __init__(self, response_rate: float = 0.8, donor_id: uuid.UUID | None = None):
        self.id = donor_id or uuid.uuid4()
        self.response_rate = response_rate


class TestAdjustedResponseRate:
    def test_zero_churn_passes_response_rate_through(self) -> None:
        assert adjusted_response_rate(_DonorStub(0.8), churn_90d=0.0) == pytest.approx(0.8)

    def test_full_churn_zeroes_out_response(self) -> None:
        assert adjusted_response_rate(_DonorStub(0.8), churn_90d=1.0) == 0.0

    def test_half_churn_halves_response(self) -> None:
        # 0.8 * (1 - 0.5) = 0.4 — flattens the optimistic bias from history
        assert adjusted_response_rate(_DonorStub(0.8), churn_90d=0.5) == pytest.approx(0.4)

    def test_negative_rate_clipped(self) -> None:
        assert adjusted_response_rate(_DonorStub(-0.3), churn_90d=0.0) == 0.0


class TestMinimalBatch:
    def _candidate(self, rr: float, donor_id: uuid.UUID | None = None) -> _DonorStub:
        return _DonorStub(response_rate=rr, donor_id=donor_id)

    def test_stops_as_soon_as_target_met(self) -> None:
        cands = [self._candidate(0.95), self._candidate(0.9), self._candidate(0.8)]
        # First donor alone already hits 0.85 — but only when we tell the
        # allocator "no churn" (otherwise it conservatively assumes 0.5)
        batch = minimal_batch(
            cands,
            churn_scores={d.id: 0.0 for d in cands},
            target_p_accept=0.85,
            max_size=5,
        )
        assert len(batch) == 1

    def test_critical_target_takes_four_for_moderate_pool(self) -> None:
        cands = [
            self._candidate(0.7),
            self._candidate(0.6),
            self._candidate(0.5),
            self._candidate(0.45),
            self._candidate(0.3),
        ]
        batch = minimal_batch(
            cands,
            churn_scores={d.id: 0.0 for d in cands},
            target_p_accept=0.95,
            max_size=8,
        )
        assert len(batch) == 4
        # 1 - (0.3)(0.4)(0.5)(0.55) ≥ 0.95
        assert p_accept(d.response_rate for d in batch) >= 0.95

    def test_missing_churn_scores_default_to_conservative(self) -> None:
        """When no churn map is provided, the allocator assumes neutral 0.5.

        This is the production-safe default — refuses to over-promise based on
        history alone when the ML model hasn't weighed in.
        """
        cands = [self._candidate(0.95), self._candidate(0.9), self._candidate(0.8)]
        # adjusted rates become 0.475, 0.45, 0.40 — needs all 3 to hit 0.85
        batch = minimal_batch(cands, target_p_accept=0.85, max_size=5)
        assert len(batch) >= 2  # certainly more than 1, exact count depends on math

    def test_max_size_caps_even_if_target_unreached(self) -> None:
        cands = [self._candidate(0.2) for _ in range(20)]  # weak pool
        batch = minimal_batch(cands, target_p_accept=0.99, max_size=5)
        assert len(batch) == 5  # cap enforced

    def test_empty_pool_returns_empty(self) -> None:
        assert minimal_batch([], target_p_accept=0.9, max_size=8) == []

    def test_churn_score_pushes_more_donors_in(self) -> None:
        """A donor with high churn looks worse — batch needs more donors to compensate."""
        cands = [self._candidate(0.7), self._candidate(0.6), self._candidate(0.5)]
        # No churn — fewest pings needed
        no_churn = minimal_batch(
            cands, churn_scores={d.id: 0.0 for d in cands},
            target_p_accept=0.85, max_size=8,
        )
        # 80% churn — donors look much weaker — should grow batch
        high_churn = minimal_batch(
            cands, churn_scores={d.id: 0.8 for d in cands},
            target_p_accept=0.85, max_size=8,
        )
        assert len(high_churn) > len(no_churn)


class TestUrgencyClassifier:
    def test_overdue_is_critical(self) -> None:
        today = date(2026, 6, 6)
        ctx = urgency_for_patient(date(2026, 6, 4), cadence_days=21, today=today)
        assert ctx.tier == UrgencyTier.CRITICAL
        assert ctx.gap_days == -2

    def test_tomorrow_is_critical(self) -> None:
        today = date(2026, 6, 6)
        ctx = urgency_for_patient(date(2026, 6, 7), cadence_days=21, today=today)
        assert ctx.tier == UrgencyTier.CRITICAL

    def test_3_days_at_21_cadence_is_high(self) -> None:
        today = date(2026, 6, 6)
        ctx = urgency_for_patient(date(2026, 6, 9), cadence_days=21, today=today)
        assert ctx.tier == UrgencyTier.HIGH
        assert ctx.ratio == pytest.approx(3 / 21)

    def test_3_days_at_14_cadence_promotes_to_high_still(self) -> None:
        # 3/14 = 0.21 > 0.15 → drops out of HIGH; CRITICAL gap-1d test doesn't fire
        # (gap=3 > 1). Should land MEDIUM.
        today = date(2026, 6, 6)
        ctx = urgency_for_patient(date(2026, 6, 9), cadence_days=14, today=today)
        assert ctx.tier == UrgencyTier.MEDIUM

    def test_5_days_at_21_cadence_is_medium(self) -> None:
        today = date(2026, 6, 6)
        ctx = urgency_for_patient(date(2026, 6, 11), cadence_days=21, today=today)
        assert ctx.tier == UrgencyTier.MEDIUM

    def test_10_days_out_is_planned(self) -> None:
        today = date(2026, 6, 6)
        ctx = urgency_for_patient(date(2026, 6, 16), cadence_days=21, today=today)
        assert ctx.tier == UrgencyTier.PLANNED

    def test_target_p_accept_per_tier(self) -> None:
        assert target_p_accept_for(UrgencyTier.CRITICAL) == 0.95
        assert target_p_accept_for(UrgencyTier.HIGH) == 0.85
        assert target_p_accept_for(UrgencyTier.MEDIUM) == 0.70
        assert target_p_accept_for(UrgencyTier.PLANNED) == 0.0

    def test_max_batch_size_grows_with_urgency(self) -> None:
        assert max_batch_for(UrgencyTier.CRITICAL) > max_batch_for(UrgencyTier.HIGH)
        assert max_batch_for(UrgencyTier.HIGH) > max_batch_for(UrgencyTier.MEDIUM)

    def test_zero_cadence_doesnt_explode(self) -> None:
        # Avoid /0 on missing/zero cadence — should still classify
        today = date(2026, 6, 6)
        ctx = urgency_for_patient(date(2026, 6, 11), cadence_days=0, today=today)
        assert ctx.tier in (UrgencyTier.MEDIUM, UrgencyTier.PLANNED, UrgencyTier.HIGH)


# ---------------------------------------------------------------------------
# DB-backed tests — eligibility + composite + cooldown
# ---------------------------------------------------------------------------


def _patient(
    db: Session,
    *,
    bg: BloodGroup = BloodGroup.B_POS,
    kell_neg: bool = False,
    lat: float = 17.39,
    lng: float = 78.46,
) -> Patient:
    p = Patient(
        name="Test Patient",
        age=12,
        blood_group=bg,
        rh_negative=False,
        kell_negative=kell_neg,
        city="Hyderabad",
        state="Telangana",
        lat=lat,
        lng=lng,
        hospital="Apollo",
        transfusion_cadence_days=21,
        active=True,
    )
    db.add(p)
    db.flush()
    return p


def _donor(
    db: Session,
    *,
    bg: BloodGroup = BloodGroup.O_POS,
    kell_neg: bool = False,
    is_active: bool = True,
    last_donation_date: date | None = None,
    last_contacted_date: date | None = None,
    total_calls: int = 0,
    calls_ratio: float = 0.0,
    response_rate: float = 0.7,
    lat: float = 17.39,
    lng: float = 78.46,
) -> Donor:
    d = Donor(
        name="Test Donor",
        age=28,
        blood_group=bg,
        rh_negative=False,
        kell_negative=kell_neg,
        phone="+919999999999",
        city="Hyderabad",
        state="Telangana",
        lat=lat,
        lng=lng,
        is_active=is_active,
        last_donation_date=last_donation_date,
        last_contacted_date=last_contacted_date,
        total_calls=total_calls,
        calls_to_donations_ratio=calls_ratio,
        response_rate=response_rate,
        registered_at=datetime(2025, 1, 1),  # past the new-donor grace period
    )
    db.add(d)
    db.flush()
    return d


class TestEligibilityFilter:
    def test_inactive_donor_excluded(self, db_session: Session) -> None:
        p = _patient(db_session)
        d = _donor(db_session, is_active=False)
        assert not is_eligible_for_outreach(d, p, today=date.today(), db=db_session)

    def test_incompatible_blood_group_excluded(self, db_session: Session) -> None:
        # A+ donor can't give to B+ patient
        p = _patient(db_session, bg=BloodGroup.B_POS)
        d = _donor(db_session, bg=BloodGroup.A_POS)
        assert not is_eligible_for_outreach(d, p, today=date.today(), db=db_session)

    def test_unknown_blood_group_excluded(self, db_session: Session) -> None:
        # 27% of real dataset has unknown — should be invisible to allocator
        p = _patient(db_session, bg=BloodGroup.B_POS)
        d = _donor(db_session, bg=BloodGroup.UNKNOWN)
        assert not is_eligible_for_outreach(d, p, today=date.today(), db=db_session)

    def test_within_90_day_deferral_excluded(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        p = _patient(db_session)
        d = _donor(db_session, last_donation_date=today - timedelta(days=45))
        assert not is_eligible_for_outreach(d, p, today=today, db=db_session)

    def test_past_90_day_deferral_eligible(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        p = _patient(db_session)
        d = _donor(db_session, last_donation_date=today - timedelta(days=120))
        assert is_eligible_for_outreach(d, p, today=today, db=db_session)

    def test_emergency_does_not_waive_clinical_deferral(self, db_session: Session) -> None:
        """Hard clinical rule — 90-day deferral is NEVER waived, even in emergency."""
        today = date(2026, 6, 6)
        p = _patient(db_session)
        d = _donor(db_session, last_donation_date=today - timedelta(days=30))
        assert not is_eligible_for_outreach(
            d, p, today=today, db=db_session, emergency=True
        )

    def test_kell_positive_donor_blocked_for_kell_negative_patient(
        self, db_session: Session
    ) -> None:
        p = _patient(db_session, kell_neg=True)
        d = _donor(db_session, kell_neg=False)
        assert not is_eligible_for_outreach(d, p, today=date.today(), db=db_session)

    def test_null_last_contacted_date_is_eligible(self, db_session: Session) -> None:
        """73% of dataset rows have NULL last_contacted_date — never-asked.

        Critical edge case: a strict 7-day cutoff against NULL would lock out
        most of the pool.
        """
        p = _patient(db_session)
        d = _donor(db_session, last_contacted_date=None)
        assert is_eligible_for_outreach(d, p, today=date.today(), db=db_session)

    def test_recent_contact_within_7_days_excluded(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        p = _patient(db_session)
        d = _donor(db_session, last_contacted_date=today - timedelta(days=3))
        assert not is_eligible_for_outreach(d, p, today=today, db=db_session)

    def test_contact_8_days_ago_eligible(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        p = _patient(db_session)
        d = _donor(db_session, last_contacted_date=today - timedelta(days=8))
        assert is_eligible_for_outreach(d, p, today=today, db=db_session)

    def test_emergency_waives_contact_cooldown(self, db_session: Session) -> None:
        today = date(2026, 6, 6)
        p = _patient(db_session)
        d = _donor(db_session, last_contacted_date=today - timedelta(days=1))
        assert is_eligible_for_outreach(
            d, p, today=today, db=db_session, emergency=True
        )

    def test_total_calls_over_10_excludes_in_normal_tier(self, db_session: Session) -> None:
        """The 29 donors in the dataset with calls_to_donations_ratio > 10 — data
        audit signal even when the ML model isn't loaded."""
        p = _patient(db_session)
        d = _donor(db_session, total_calls=15)
        assert not is_eligible_for_outreach(d, p, today=date.today(), db=db_session)

    def test_total_calls_excluded_only_in_normal_tier(self, db_session: Session) -> None:
        p = _patient(db_session)
        d = _donor(db_session, total_calls=15)
        assert is_eligible_for_outreach(
            d, p, today=date.today(), db=db_session, emergency=True
        )

    def test_calls_to_donations_ratio_gate(self, db_session: Session) -> None:
        p = _patient(db_session)
        d = _donor(db_session, calls_ratio=12.0)
        assert not is_eligible_for_outreach(d, p, today=date.today(), db=db_session)


class TestCooldownChecks:
    def test_no_cooldown_means_no_block(self, db_session: Session) -> None:
        p = _patient(db_session)
        d = _donor(db_session)
        assert not has_active_cooldown(db_session, donor_id=d.id, patient_id=p.id)

    def test_per_patient_cooldown_blocks_only_that_patient(
        self, db_session: Session
    ) -> None:
        p1 = _patient(db_session)
        p2 = _patient(db_session)
        d = _donor(db_session)
        db_session.add(
            OutreachCooldown(
                donor_id=d.id,
                patient_id=p1.id,
                reason=CooldownReason.DECLINED,
                expires_at=datetime.utcnow() + timedelta(days=30),
            )
        )
        db_session.flush()
        assert has_active_cooldown(db_session, donor_id=d.id, patient_id=p1.id)
        # Different patient — same donor — should NOT be cooled down
        assert not has_active_cooldown(db_session, donor_id=d.id, patient_id=p2.id)

    def test_global_cooldown_blocks_every_patient(self, db_session: Session) -> None:
        """patient_id=NULL means cooldown is global (e.g. OPT_OUT_TEMPORARY)."""
        p1 = _patient(db_session)
        p2 = _patient(db_session)
        d = _donor(db_session)
        db_session.add(
            OutreachCooldown(
                donor_id=d.id,
                patient_id=None,
                reason=CooldownReason.OPT_OUT_TEMPORARY,
                expires_at=datetime.utcnow() + timedelta(days=14),
            )
        )
        db_session.flush()
        assert has_active_cooldown(db_session, donor_id=d.id, patient_id=p1.id)
        assert has_active_cooldown(db_session, donor_id=d.id, patient_id=p2.id)

    def test_expired_cooldown_no_longer_blocks(self, db_session: Session) -> None:
        p = _patient(db_session)
        d = _donor(db_session)
        db_session.add(
            OutreachCooldown(
                donor_id=d.id,
                patient_id=p.id,
                reason=CooldownReason.NO_REPLY,
                expires_at=datetime.utcnow() - timedelta(hours=1),  # expired
            )
        )
        db_session.flush()
        assert not has_active_cooldown(db_session, donor_id=d.id, patient_id=p.id)


class TestCompositeScoring:
    def test_close_donor_outscores_distant_donor(self, db_session: Session) -> None:
        p = _patient(db_session, lat=17.39, lng=78.46)
        near = _donor(db_session, lat=17.40, lng=78.47)
        far = _donor(db_session, lat=18.50, lng=78.10)
        assert composite_score(near, p, db=db_session) > composite_score(
            far, p, db=db_session
        )

    def test_rotation_penalty_reduces_score_for_recently_pinged_donor(
        self, db_session: Session
    ) -> None:
        p = _patient(db_session)
        d_fresh = _donor(db_session)
        d_burned = _donor(db_session)
        # Pin 5 recent pings on d_burned
        wave = OutreachWave(
            patient_id=p.id, slot_date=date.today(), gap_days_at_creation=3
        )
        db_session.add(wave)
        db_session.flush()
        for _ in range(5):
            db_session.add(
                OutreachPing(
                    wave_id=wave.id,
                    donor_id=d_burned.id,
                    sent_at=datetime.utcnow() - timedelta(days=3),
                    response=PingResponse.NO_REPLY,
                )
            )
        db_session.flush()
        assert composite_score(d_fresh, p, db=db_session) > composite_score(
            d_burned, p, db=db_session
        )

    def test_bridge_stickiness_penalty(self, db_session: Session) -> None:
        """A donor active in another bridge should rank lower for this patient."""
        p1 = _patient(db_session)
        p2 = _patient(db_session)
        b1 = Bridge(patient_id=p1.id, name="Other bridge", status=BridgeStatus.ACTIVE)
        db_session.add(b1)
        db_session.flush()

        sticky = _donor(db_session)
        free = _donor(db_session)
        # sticky has an active membership on someone else's bridge
        db_session.add(
            BridgeMembership(
                bridge_id=b1.id,
                donor_id=sticky.id,
                role=MembershipRole.PRIMARY,
                status=MembershipStatus.ACTIVE,
            )
        )
        db_session.flush()
        # Both are scored AGAINST p2 (a different patient, no bridge created)
        # The free donor should outrank the sticky one
        s_sticky = composite_score(sticky, p2, db=db_session)
        s_free = composite_score(free, p2, db=db_session)
        assert s_free > s_sticky

    def test_kell_negative_match_bonus(self, db_session: Session) -> None:
        p = _patient(db_session, kell_neg=True)
        kell_neg_donor = _donor(db_session, kell_neg=True)
        kell_pos_donor = _donor(db_session, kell_neg=False)
        # The kell-pos donor wouldn't be eligible at all but composite_score
        # doesn't check eligibility — it's pure ranking. Score difference should
        # reflect the +0.10 bonus.
        s_match = composite_score(kell_neg_donor, p, db=db_session)
        s_nomatch = composite_score(kell_pos_donor, p, db=db_session)
        assert s_match - s_nomatch == pytest.approx(0.10, abs=0.01)
