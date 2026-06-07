"""E8.1 — caregiver auto-reply tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.integrations.ses_inbound import strip_quoted_content
from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    CaregiverRelation,
    ContactChannel,
    EmailMessage,
    Patient,
    ReplyIntent,
)
from app.services.caregiver_auto_reply import send_caregiver_auto_reply


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")


def _make_patient(db: Session) -> Patient:
    p = Patient(
        name="Riya Sharma", age=8, blood_group=BloodGroup.B_POS,
        rh_negative=False, kell_negative=False,
        city="Hyderabad", state="Telangana", lat=17.39, lng=78.46,
        hospital="Rainbow Hospitals", transfusion_cadence_days=21,
        last_transfusion_date=date(2026, 5, 15), active=True,
        caregiver_name="Anita Sharma", caregiver_phone="+919900000077",
        caregiver_email="anita@example.com",
        caregiver_relation=CaregiverRelation.MOTHER,
        caregiver_preferred_channel=ContactChannel.EMAIL,
    )
    db.add(p); db.flush()
    db.add(Bridge(patient_id=p.id, name="r", status=BridgeStatus.ACTIVE)); db.commit()
    return p


def test_resolved_intent_uses_cancelled_template(db_session: Session):
    patient = _make_patient(db_session)
    out = send_caregiver_auto_reply(
        db_session,
        patient=patient,
        intent=ReplyIntent.STOP,
        incoming_body="STOP we're sorted",
        incoming_subject="Re: Bridge update",
    )
    assert out.sent is True
    assert out.template_key == "caregiver_auto_reply_resolved"
    em = db_session.query(EmailMessage).filter(EmailMessage.direction == "outbound").one()
    assert "cancelled" in em.body.lower()
    assert em.subject == "Outreach cancelled"


def test_urgent_intent_routes_to_call_template(db_session: Session):
    patient = _make_patient(db_session)
    out = send_caregiver_auto_reply(
        db_session,
        patient=patient,
        intent=ReplyIntent.MEDICAL_DEFER,
        incoming_body="urgent help needed",
        incoming_subject="Re: Bridge update",
    )
    assert out.template_key == "caregiver_auto_reply_urgent"
    em = db_session.query(EmailMessage).filter(EmailMessage.direction == "outbound").one()
    assert "URGENT" in em.subject
    assert "15 minutes" in em.body or "15 min" in em.body


def test_question_intent_falls_back_when_bedrock_unavailable(db_session: Session):
    """If Bedrock is in mock mode the auto-reply uses the fallback template
    rather than crashing."""
    patient = _make_patient(db_session)
    with patch(
        "app.agent.llm_client.chat",
        side_effect=Exception("Bedrock mocked"),
    ):
        out = send_caregiver_auto_reply(
            db_session,
            patient=patient,
            intent=ReplyIntent.UNRELATED_QUESTION,
            incoming_body="What time should we come for the transfusion?",
            incoming_subject="Re: Bridge update",
        )
    assert out.sent is True
    assert out.template_key == "caregiver_auto_reply_question_fallback"
    em = db_session.query(EmailMessage).filter(EmailMessage.direction == "outbound").one()
    assert "coordinator will reply" in em.body.lower()


def test_question_intent_uses_bedrock_when_available(db_session: Session):
    """When Bedrock returns a string, the body is that string."""
    patient = _make_patient(db_session)
    class _FakeResponse:
        text = "Next transfusion is on June 12 at Rainbow Hospitals around 10am."
    with patch(
        "app.agent.llm_client.chat",
        return_value=_FakeResponse(),
    ):
        out = send_caregiver_auto_reply(
            db_session,
            patient=patient,
            intent=ReplyIntent.UNRELATED_QUESTION,
            incoming_body="When is the next transfusion?",
            incoming_subject="Re: Bridge update",
        )
    assert out.sent is True
    assert out.template_key == "caregiver_auto_reply_question_bedrock"
    em = db_session.query(EmailMessage).filter(EmailMessage.direction == "outbound").one()
    assert "Rainbow Hospitals" in em.body
    assert "June 12" in em.body


# ---------- strip_quoted_content ----------


def test_strip_gmail_reply_quote():
    body = (
        "What time should we come for the transfusion?\r\n\r\n"
        "On Sun, 7 Jun 2026 at 04:11, <ops@bridge-os.click> wrote:\r\n\r\n"
        "> Hi Gunaputra,\r\n>\r\n> Riya needs a donor — reply STOP to cancel.\r\n"
    )
    out = strip_quoted_content(body)
    assert "transfusion" in out
    assert "STOP" not in out
    assert "ops@bridge-os.click" not in out


def test_strip_outlook_reply_quote():
    body = (
        "Thanks for letting us know.\n\n"
        "From: ops@bridge-os.click\nSent: 7 June\nSubject: Bridge update\n\n"
        "Original text..."
    )
    out = strip_quoted_content(body)
    assert "Thanks for letting us know" in out
    assert "Original text" not in out


def test_strip_top_quoted_lines_at_end():
    body = "Plain reply.\n> quoted line 1\n> quoted line 2"
    out = strip_quoted_content(body)
    assert "Plain reply" in out
    assert "quoted" not in out


def test_strip_returns_unchanged_when_no_markers():
    body = "Hi, just a quick question — what time should we come?"
    assert strip_quoted_content(body) == body
