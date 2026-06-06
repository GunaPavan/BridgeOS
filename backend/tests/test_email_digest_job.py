"""Phase E2 — auto_caregiver_email_digest scheduler job + dispatcher tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    CaregiverRelation,
    EmailMessage,
    Patient,
)


@pytest.fixture
def mock_ses_disabled(monkeypatch):
    """Force mock mode so tests don't hit SES."""
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    monkeypatch.delenv("SES_FROM_EMAIL", raising=False)


def _make_patient(
    db: Session,
    *,
    caregiver_email: str | None = "caregiver@example.com",
    active: bool = True,
) -> Patient:
    p = Patient(
        name="Test Patient",
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
        active=active,
        caregiver_name="Caregiver A",
        caregiver_phone="+919999990001",
        caregiver_email=caregiver_email,
        caregiver_relation=CaregiverRelation.MOTHER,
    )
    db.add(p)
    db.flush()
    db.add(Bridge(patient_id=p.id, name="Bridge", status=BridgeStatus.ACTIVE))
    db.flush()
    return p


def test_digest_sends_one_email_per_qualifying_patient(
    db_session: Session, mock_ses_disabled
) -> None:
    from app.scheduler.jobs import auto_caregiver_email_digest

    _make_patient(db_session, caregiver_email="a@x.com")
    _make_patient(db_session, caregiver_email="b@y.com")
    _make_patient(db_session, caregiver_email=None)  # skipped
    _make_patient(db_session, caregiver_email="c@z.com", active=False)  # skipped
    db_session.commit()

    result = auto_caregiver_email_digest(
        db=db_session, now=datetime(2026, 6, 7, 2, 30, 0)
    )
    assert result.items_processed == 2
    assert result.payload["sent"] == 2

    emails = db_session.query(EmailMessage).all()
    assert len(emails) == 2
    recipients = sorted(e.recipient_email for e in emails)
    assert recipients == ["a@x.com", "b@y.com"]
    for e in emails:
        assert e.template_key == "caregiver_daily_digest"
        assert e.is_mock is True
        assert e.status == "mocked"


def test_digest_skips_patient_without_email(
    db_session: Session, mock_ses_disabled
) -> None:
    from app.scheduler.jobs import auto_caregiver_email_digest

    _make_patient(db_session, caregiver_email=None)
    db_session.commit()

    result = auto_caregiver_email_digest(
        db=db_session, now=datetime(2026, 6, 7, 2, 30, 0)
    )
    # Job query already filters out None — so the loop never sees it
    assert result.items_processed == 0
    assert db_session.query(EmailMessage).count() == 0


def test_dispatcher_skipped_outcome_when_no_email(
    db_session: Session, mock_ses_disabled
) -> None:
    from app.services.email_dispatcher import send_caregiver_daily_digest

    p = _make_patient(db_session, caregiver_email=None)
    outcome = send_caregiver_daily_digest(db_session, patient=p)
    assert outcome.sent is False
    assert outcome.status == "skipped"
    assert "no caregiver_email" in (outcome.error_message or "")


def test_emergency_alert_dispatch(db_session: Session, mock_ses_disabled) -> None:
    from app.services.email_dispatcher import send_caregiver_emergency_alert

    p = _make_patient(db_session, caregiver_email="urgent@example.com")
    outcome = send_caregiver_emergency_alert(
        db_session, patient=p, slot_date=date(2026, 6, 9), tier_label="Tier 3"
    )
    assert outcome.sent
    e = db_session.query(EmailMessage).one()
    assert e.recipient_email == "urgent@example.com"
    assert e.template_key == "caregiver_emergency_alert"


def test_coordinator_failure_dispatch(
    db_session: Session, mock_ses_disabled
) -> None:
    from app.services.email_dispatcher import send_coordinator_failure_alert

    outcome = send_coordinator_failure_alert(
        db_session,
        coordinator_email="ops@example.com",
        patient_name="Riya",
        slot_date=date(2026, 6, 9),
        tier_label="Tier 3",
        wave_id="abcd1234",
        pings_sent=12,
        pings_accepted=0,
        pings_declined=4,
        pings_no_reply=8,
    )
    assert outcome.sent
    e = db_session.query(EmailMessage).one()
    assert e.recipient_email == "ops@example.com"
    assert e.template_key == "coordinator_failure_alert"
