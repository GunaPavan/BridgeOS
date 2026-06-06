"""E7 — inbound email handler tests.

Exercises the full pipeline: parsed email → patient match → classifier →
SNS topic publish → EmailMessage audit row.

Bedrock is mocked via the keyword fallback (sufficient for these tests).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy.orm import Session

from app.integrations import sns_client
from app.integrations.ses_inbound import ParsedInboundEmail
from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    CaregiverRelation,
    ContactChannel,
    EmailMessage,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    PingResponse,
    ReplyClassification,
    UrgencyTier,
)
from app.services.inbound_email_handler import process_inbound_email


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    sns_client._reset_mock_topics_for_tests()


def _make_patient(db: Session, *, email: str | None = "anita@example.com") -> Patient:
    p = Patient(
        name="Riya Sharma", age=8, blood_group=BloodGroup.B_POS,
        rh_negative=False, kell_negative=False,
        city="Hyderabad", state="Telangana", lat=17.39, lng=78.46,
        hospital="Rainbow", transfusion_cadence_days=21,
        last_transfusion_date=date(2026, 5, 1), active=True,
        caregiver_name="Anita Sharma", caregiver_phone="+919900000077",
        caregiver_email=email,
        caregiver_relation=CaregiverRelation.MOTHER,
        caregiver_preferred_channel=ContactChannel.EMAIL,
    )
    db.add(p)
    db.flush()
    bridge = Bridge(patient_id=p.id, name="Riya Bridge", status=BridgeStatus.ACTIVE)
    db.add(bridge)
    db.flush()
    return p


def _make_active_wave(db: Session, patient: Patient) -> OutreachWave:
    bridge = patient.bridge
    wave = OutreachWave(
        bridge_id=bridge.id, patient_id=patient.id,
        slot_date=date.today(),
        status=OutreachWaveStatus.ACTIVE,
        tier=OutreachTier.TIER_1, urgency=UrgencyTier.HIGH,
    )
    db.add(wave)
    db.flush()
    return wave


def _stub_email(*, body: str, from_email: str = "anita@example.com") -> ParsedInboundEmail:
    return ParsedInboundEmail(
        from_email=from_email,
        to_email="ops@bridgeos.example",
        subject="Re: Today's bridge update",
        body_text=body,
        body_html=None,
        message_id=f"test-msg-{hash(body) & 0xFFFFFF:x}",
        received_at=datetime.utcnow(),
    )


def test_process_resolved_reply_publishes_topic_and_persists_email(
    db_session: Session,
):
    patient = _make_patient(db_session)
    db_session.commit()

    parsed = _stub_email(
        body="STOP - we're all sorted, thanks. Please cancel the alert.",
    )
    result = process_inbound_email(db_session, email_obj=parsed)

    assert result.matched_patient_id == patient.id
    assert result.topic_published == "caregiver-reply-resolved"
    assert result.sns_message_id  # something was published
    # EmailMessage row was created with direction=inbound
    em = db_session.get(EmailMessage, result.persisted_email_id)
    assert em is not None
    assert em.direction == "inbound"
    assert em.caregiver_for_patient_id == patient.id


def test_unknown_sender_persists_but_does_not_publish(db_session: Session):
    parsed = _stub_email(
        body="Hi, who are you?", from_email="stranger@nowhere.example"
    )
    result = process_inbound_email(db_session, email_obj=parsed)
    assert result.matched_patient_id is None
    assert result.topic_published is None
    assert result.reason == "unknown_sender"
    # Audit row still exists so an operator can investigate
    assert result.persisted_email_id is not None


def test_duplicate_message_id_is_idempotent(db_session: Session):
    patient = _make_patient(db_session)
    db_session.commit()

    parsed = _stub_email(body="STOP - sorted")
    first = process_inbound_email(db_session, email_obj=parsed)
    second = process_inbound_email(db_session, email_obj=parsed)
    assert first.persisted_email_id == second.persisted_email_id
    assert second.reason == "duplicate_message_id"
    # Only one EmailMessage row created
    n = db_session.query(EmailMessage).filter(
        EmailMessage.direction == "inbound"
    ).count()
    assert n == 1


def test_caregiver_resolved_subscriber_cancels_pending_outreach(
    db_session: Session,
):
    """The full automation loop: subscriber-side effect must cancel waves.

    We invoke the subscriber with a session_factory that returns the test
    DB session so the writes land where the assertions can see them.
    """
    from contextlib import contextmanager

    # Force-import subscribers so they register
    from app.events import subscribers  # noqa: F401
    from app.events.subscribers.caregiver_email_actions import (
        cancel_outreach_when_caregiver_resolved,
    )

    patient = _make_patient(db_session)
    wave = _make_active_wave(db_session, patient)
    db_session.commit()

    # Wrap the test session as a callable factory that supports `with`
    @contextmanager
    def _session_factory():
        try:
            yield db_session
        finally:
            pass  # the test owns the lifecycle

    body = {"patient_id": str(patient.id), "email_message_id": "x", "body_excerpt": ""}
    cancel_outreach_when_caregiver_resolved(body, _session_factory)

    db_session.expire_all()
    refreshed = db_session.get(OutreachWave, wave.id)
    status_val = getattr(refreshed.status, "value", str(refreshed.status))
    assert status_val == OutreachWaveStatus.EXPIRED.value
