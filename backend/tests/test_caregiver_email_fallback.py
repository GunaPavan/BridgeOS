"""Phase E2 — WhatsApp → SES fallback.

When Twilio is in mock mode (no creds, dev / hackathon laptop) the caregiver
never actually receives the WhatsApp message. If we have their email, we
mirror the body via SES so the demo and dev environments actually deliver
to a human.
"""

from __future__ import annotations

from datetime import date

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


@pytest.fixture(autouse=True)
def _force_mock_aws(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    monkeypatch.delenv("SES_FROM_EMAIL", raising=False)


def _make_patient_with_bridge(
    db_session: Session, *, caregiver_email: str | None
) -> Patient:
    patient = Patient(
        name="Riya Sharma",
        age=8,
        blood_group=BloodGroup.B_POS,
        rh_negative=False,
        kell_negative=False,
        city="Hyderabad",
        state="Telangana",
        lat=17.39,
        lng=78.46,
        hospital="Rainbow Hospitals",
        transfusion_cadence_days=21,
        last_transfusion_date=date(2026, 5, 20),
        active=True,
        caregiver_name="Anita Sharma",
        caregiver_phone="+919900000007",
        caregiver_email=caregiver_email,
        caregiver_relation=CaregiverRelation.MOTHER,
        preferred_language="en",
    )
    db_session.add(patient)
    db_session.flush()
    bridge = Bridge(patient_id=patient.id, name="Test Bridge", status=BridgeStatus.ACTIVE)
    db_session.add(bridge)
    db_session.flush()
    return patient


def test_fallback_fires_when_twilio_mocked_and_email_present(db_session: Session):
    """The canonical happy path: Twilio is mocked, caregiver_email is set,
    we expect both the WhatsAppMessage row AND an EmailMessage row."""
    from app.services.caregiver_notifications import send_caregiver_template

    patient = _make_patient_with_bridge(db_session, caregiver_email="riya.mom@example.com")
    bridge = patient.bridge
    assert bridge is not None

    result = send_caregiver_template(
        db_session,
        patient=patient,
        bridge=bridge,
        template_key="recruit_success_caregiver",
        added_donor_name="Vikram K",
        commit=True,
    )

    assert result.email_fallback_sent is True
    assert result.email_fallback_message_id
    # And the EmailMessage row exists
    em = (
        db_session.query(EmailMessage)
        .filter(EmailMessage.caregiver_for_patient_id == patient.id)
        .one()
    )
    assert em.recipient_email == "riya.mom@example.com"
    assert em.template_key.endswith("__email_fallback")
    assert "Bridge update" in em.subject
    assert em.is_mock is True


def test_no_fallback_when_caregiver_email_missing(db_session: Session):
    """If caregiver_email isn't set we must not invent an address."""
    from app.services.caregiver_notifications import send_caregiver_template

    patient = _make_patient_with_bridge(db_session, caregiver_email=None)
    bridge = patient.bridge
    assert bridge is not None

    result = send_caregiver_template(
        db_session,
        patient=patient,
        bridge=bridge,
        template_key="recruit_success_caregiver",
        added_donor_name="Vikram K",
        commit=True,
    )

    assert result.email_fallback_sent is False
    assert result.email_fallback_message_id is None
    assert db_session.query(EmailMessage).count() == 0


def test_no_fallback_when_twilio_is_live(db_session: Session, monkeypatch):
    """If Twilio is actually live we should NOT also email — the caregiver
    already got the WhatsApp."""
    from app.integrations import twilio_client
    from app.services.caregiver_notifications import send_caregiver_template

    # Pretend Twilio is live and the send succeeded
    def _live_send(*, to_number, body):
        return twilio_client.SendResult(
            sid="SM-live-1234",
            status="queued",
            is_mock=False,
        )

    monkeypatch.setattr(twilio_client, "send_whatsapp", _live_send)

    patient = _make_patient_with_bridge(db_session, caregiver_email="riya.mom@example.com")
    bridge = patient.bridge
    assert bridge is not None

    result = send_caregiver_template(
        db_session,
        patient=patient,
        bridge=bridge,
        template_key="recruit_success_caregiver",
        added_donor_name="Vikram K",
        commit=True,
    )

    # No email — live WhatsApp succeeded
    assert result.email_fallback_sent is False
    assert db_session.query(EmailMessage).count() == 0
