"""E7 — /emails/inbound-* endpoint tests."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations import sns_client
from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    CaregiverRelation,
    ContactChannel,
    Patient,
)


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    sns_client._reset_mock_topics_for_tests()
    # Touch subscribers so registry is hot
    from app.events import subscribers  # noqa: F401


def _make_caregiver(db: Session, email: str = "anita@example.com") -> Patient:
    p = Patient(
        name="Riya", age=8, blood_group=BloodGroup.B_POS,
        rh_negative=False, kell_negative=False,
        city="Hyderabad", state="Telangana", lat=17.39, lng=78.46,
        hospital="Rainbow", transfusion_cadence_days=21,
        last_transfusion_date=date(2026, 5, 1), active=True,
        caregiver_name="Anita", caregiver_phone="+919900000077",
        caregiver_email=email,
        caregiver_relation=CaregiverRelation.MOTHER,
        caregiver_preferred_channel=ContactChannel.EMAIL,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_inbound_webhook_classifies_and_publishes(
    client: TestClient, db_session: Session
):
    patient = _make_caregiver(db_session)

    r = client.post(
        "/emails/inbound-webhook",
        json={
            "from_email": "anita@example.com",
            "to_email": "ops@bridgeos.example",
            "subject": "Re: Update for Riya",
            "body_text": "STOP - we are sorted",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["matched_patient_id"] == str(patient.id)
    assert body["topic_published"] == "caregiver-reply-resolved"


def test_inbound_webhook_unknown_sender_returns_reason(client: TestClient):
    r = client.post(
        "/emails/inbound-webhook",
        json={
            "from_email": "stranger@nowhere.example",
            "body_text": "anyone there?",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["matched_patient_id"] is None
    assert body["reason"] == "unknown_sender"


def test_inbound_raw_parses_mime_and_dispatches(
    client: TestClient, db_session: Session
):
    _make_caregiver(db_session)

    raw = (
        b"From: Anita <anita@example.com>\r\n"
        b"To: ops@bridgeos.example\r\n"
        b"Subject: Re: bridge update\r\n"
        b"Message-ID: <raw-mime-test@example.com>\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"STOP we already found a donor\r\n"
    )
    r = client.post(
        "/emails/inbound-raw",
        content=raw,
        headers={"content-type": "message/rfc822"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["topic_published"] == "caregiver-reply-resolved"


def test_inbound_raw_empty_body_400(client: TestClient):
    r = client.post(
        "/emails/inbound-raw",
        content=b"",
        headers={"content-type": "message/rfc822"},
    )
    assert r.status_code == 400


def test_list_inbound_returns_processed_emails(
    client: TestClient, db_session: Session
):
    _make_caregiver(db_session)
    client.post(
        "/emails/inbound-webhook",
        json={"from_email": "anita@example.com", "body_text": "STOP sorted"},
    )
    r = client.get("/emails/inbound?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 1
    assert body[0]["from_email"] == "anita@example.com"
