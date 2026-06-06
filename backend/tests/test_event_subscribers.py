"""Phase E4 — in-process EventDispatcher + subscriber tests."""

from __future__ import annotations

import time
import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    CooldownReason,
    Donor,
    OutreachCooldown,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    PingResponse,
    UrgencyTier,
)


class _NoCloseSession:
    def __init__(self, session: Session) -> None:
        self._s = session

    def __enter__(self) -> Session:
        return self._s

    def __exit__(self, *args) -> None:
        return None


@pytest.fixture
def factory(db_session: Session):
    return lambda: _NoCloseSession(db_session)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    from app.integrations import sns_client
    sns_client._reset_mock_topics_for_tests()
    # Import subscribers so they register
    from app.events import subscribers  # noqa: F401
    yield


def _make_donor(db: Session) -> Donor:
    d = Donor(
        name="D", age=29, blood_group=BloodGroup.O_POS,
        rh_negative=False, kell_negative=False, phone="+919999999000",
        city="Hyderabad", state="Telangana", lat=17.4, lng=78.5,
        is_active=True, response_rate=0.6, registered_at=datetime(2025, 1, 1),
    )
    db.add(d); db.flush()
    return d


def _drain_dispatcher_once(factory):
    """Spin up a dispatcher tick manually instead of using the daemon thread —
    keeps tests deterministic."""
    from app.events.dispatcher import EventDispatcher

    ed = EventDispatcher(session_factory=factory, poll_interval_seconds=0.01)
    ed._cursor = 0  # see all events
    ed._tick()
    return ed.stats


def test_out_of_town_subscriber_sets_cooldown(db_session: Session, factory):
    from app.events.publishers import publish_donor_reply_out_of_town

    donor = _make_donor(db_session)
    publish_donor_reply_out_of_town(donor_id=donor.id)
    _drain_dispatcher_once(factory)

    cds = db_session.execute(
        select(OutreachCooldown).where(OutreachCooldown.donor_id == donor.id)
    ).scalars().all()
    assert len(cds) == 1
    assert cds[0].reason == CooldownReason.OPT_OUT_TEMPORARY


def test_medical_defer_subscriber_sets_14_day_cooldown(
    db_session: Session, factory
):
    from app.events.publishers import publish_donor_reply_medical_defer

    donor = _make_donor(db_session)
    publish_donor_reply_medical_defer(donor_id=donor.id, reason="fever")
    _drain_dispatcher_once(factory)

    cd = db_session.execute(
        select(OutreachCooldown).where(OutreachCooldown.donor_id == donor.id)
    ).scalar_one()
    # 14 days ± 1 minute
    delta = (cd.expires_at - datetime.utcnow()).total_seconds()
    assert 14 * 86400 - 120 <= delta <= 14 * 86400 + 60
    assert "fever" in (cd.notes or "")


def test_opt_out_subscriber_sets_365_day_cooldown(db_session: Session, factory):
    from app.events.publishers import publish_donor_reply_opt_out

    donor = _make_donor(db_session)
    publish_donor_reply_opt_out(donor_id=donor.id)
    _drain_dispatcher_once(factory)

    cd = db_session.execute(
        select(OutreachCooldown).where(OutreachCooldown.donor_id == donor.id)
    ).scalar_one()
    delta = (cd.expires_at - datetime.utcnow()).total_seconds()
    assert delta > 360 * 86400


def test_ema_subscriber_bumps_response_rate(db_session: Session, factory):
    from app.events.publishers import publish_donor_reply_accept

    donor = _make_donor(db_session)
    before = donor.response_rate
    publish_donor_reply_accept(donor_id=donor.id)
    _drain_dispatcher_once(factory)

    db_session.refresh(donor)
    assert donor.response_rate > before


def test_cooldown_idempotent_no_double_insert(db_session: Session, factory):
    """Two publishes of the same event → only one active cooldown."""
    from app.events.publishers import publish_donor_reply_out_of_town

    donor = _make_donor(db_session)
    publish_donor_reply_out_of_town(donor_id=donor.id)
    publish_donor_reply_out_of_town(donor_id=donor.id)
    _drain_dispatcher_once(factory)

    cds = db_session.execute(
        select(OutreachCooldown).where(OutreachCooldown.donor_id == donor.id)
    ).scalars().all()
    assert len(cds) == 1
