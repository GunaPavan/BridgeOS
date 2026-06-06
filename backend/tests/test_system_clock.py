"""Tests for the dataset-anchored system clock."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import BloodGroup, Donor
from app.system_clock import (
    _query_reference_date,
    invalidate_cache,
    reference_label,
    system_clock_info,
    today,
)


def _add_donor(db: Session, *, last_contacted: date | None, last_donation: date | None):
    """Insert a minimal donor row with the dates we care about."""
    d = Donor(
        name="Test Donor",
        age=30,
        blood_group=BloodGroup.O_POS,
        rh_negative=False,
        kell_negative=False,
        phone="+910000000000",
        city="Test City",
        state="Test",
        lat=17.0,
        lng=78.0,
        is_active=True,
        last_contacted_date=last_contacted,
        last_donation_date=last_donation,
    )
    db.add(d)
    db.flush()
    return d


def test_query_reference_date_picks_most_recent_donor_event(db_session: Session) -> None:
    """Most recent of last_contacted_date and last_donation_date wins, +7d buffer."""
    invalidate_cache()
    wall_today = date.today()
    _add_donor(db_session, last_contacted=wall_today - timedelta(days=200), last_donation=None)
    _add_donor(db_session, last_contacted=None, last_donation=wall_today - timedelta(days=100))
    db_session.commit()

    ref = _query_reference_date(db_session)
    # The most recent event is 100 days ago, +7 day buffer = 93 days ago
    # (or returns None if the gap is < 30, which it isn't here).
    assert ref == wall_today - timedelta(days=100) + timedelta(days=7)


def test_no_anchor_when_data_is_within_30_days_of_wall_clock(db_session: Session) -> None:
    """Recent in-memory test data should NOT trigger anchoring."""
    invalidate_cache()
    wall_today = date.today()
    _add_donor(db_session, last_contacted=wall_today - timedelta(days=5), last_donation=None)
    db_session.commit()
    # Even with anchor + 7d buffer the gap to wall-clock is too small to anchor.
    assert _query_reference_date(db_session) is None


def test_future_dated_data_is_capped_to_wall_clock(db_session: Session) -> None:
    """Bad rows (future-dated 2029-09-30 in the real CSV) must not poison the anchor."""
    invalidate_cache()
    wall_today = date.today()
    _add_donor(
        db_session,
        last_contacted=wall_today - timedelta(days=200),
        last_donation=wall_today + timedelta(days=200),  # future-dated junk
    )
    db_session.commit()
    ref = _query_reference_date(db_session)
    # The future date is filtered out; the valid contact date wins.
    assert ref == wall_today - timedelta(days=200) + timedelta(days=7)


def test_today_returns_wall_clock_when_db_is_empty(db_session: Session) -> None:
    """Empty DB → fall back to wall-clock today."""
    invalidate_cache()
    # db_session is empty for this test — no donors added
    assert today(db_session) == date.today()


def test_clock_endpoint_returns_expected_keys(client: TestClient) -> None:
    """The /system/clock endpoint returns the expected payload shape."""
    body = client.get("/system/clock").json()
    for key in ("today", "wall_clock", "is_anchored", "days_anchored_back", "label"):
        assert key in body
    assert isinstance(body["today"], str)
    assert isinstance(body["is_anchored"], bool)


def test_patient_days_until_transfusion_returns_none_when_severely_stale(
    db_session: Session,
) -> None:
    """A transfusion scheduled >30 days in the past relative to the anchor must
    NOT display a misleading 'X days overdue' number — return None instead."""
    from app.models import Bridge, BridgeStatus, Patient

    # Insert a donor so the anchor is stale (>= 30 days back)
    invalidate_cache()
    wall_today = date.today()
    _add_donor(
        db_session,
        last_contacted=wall_today - timedelta(days=100),  # 100 days behind
        last_donation=None,
    )

    # Patient with a transfusion scheduled 200 days ago — definitely stale
    p = Patient(
        name="Stale Patient",
        age=10,
        blood_group=BloodGroup.O_POS,
        rh_negative=False,
        kell_negative=False,
        city="Test",
        state="Test",
        lat=17.0,
        lng=78.0,
        hospital="Test Hospital",
        transfusion_cadence_days=18,
        last_transfusion_date=wall_today - timedelta(days=200),
        active=True,
    )
    db_session.add(p)
    db_session.flush()

    # next_transfusion_date = 200d ago + 18d = 182d ago — well past the stale threshold
    assert p.days_until_transfusion is None
