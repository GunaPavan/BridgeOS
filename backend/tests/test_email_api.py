"""Phase E2 — /emails/* API tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import EmailMessage


def _seed(
    db: Session,
    *,
    template_key: str = "caregiver_daily_digest",
    status: str = "sent",
    recipient: str = "a@x.com",
) -> EmailMessage:
    row = EmailMessage(
        direction="outbound",
        recipient_email=recipient,
        from_email="ops@team019.example",
        subject="Daily update",
        body="Body",
        template_key=template_key,
        language="en",
        ses_message_id="x",
        status=status,
        is_mock=(status == "mocked"),
        created_at=datetime.utcnow(),
        sent_at=datetime.utcnow() if status in ("sent", "mocked") else None,
    )
    db.add(row)
    db.flush()
    return row


def test_list_emails_empty(client: TestClient) -> None:
    r = client.get("/emails")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_list_emails_with_filter(client: TestClient, db_session: Session) -> None:
    _seed(db_session, status="sent")
    _seed(db_session, status="failed")
    _seed(db_session, status="mocked", recipient="b@y.com")

    r = client.get("/emails?status=sent")
    assert r.json()["total"] == 1

    r = client.get("/emails?recipient=b@y.com")
    assert r.json()["total"] == 1

    r = client.get("/emails?template_key=caregiver_daily_digest")
    assert r.json()["total"] == 3


def test_get_single_email(client: TestClient, db_session: Session) -> None:
    row = _seed(db_session)
    r = client.get(f"/emails/{row.id}")
    assert r.status_code == 200
    assert r.json()["recipient_email"] == "a@x.com"


def test_get_email_404(client: TestClient) -> None:
    import uuid as _u
    r = client.get(f"/emails/{_u.uuid4()}")
    assert r.status_code == 404


def test_distribution(client: TestClient, db_session: Session) -> None:
    _seed(db_session, template_key="caregiver_daily_digest", status="sent")
    _seed(db_session, template_key="caregiver_daily_digest", status="failed")
    _seed(db_session, template_key="caregiver_emergency_alert", status="mocked")
    r = client.get("/emails/distribution?window_days=30")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["sent"] == 1
    assert body["failed"] == 1
    assert body["mocked"] == 1
    by_template = {b["template_key"]: b for b in body["by_template"]}
    assert by_template["caregiver_daily_digest"]["sent"] == 1
    assert by_template["caregiver_daily_digest"]["failed"] == 1


def test_test_email_returns_mock_in_mock_mode(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    r = client.post(
        "/emails/test",
        json={"recipient": "test@x.com", "subject": "hi", "body": "body"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_mock"] is True
    assert body["status"] == "mocked"
    # Persisted
    row = db_session.get(EmailMessage, body["persisted_id"])
    assert row is not None
    assert row.recipient_email == "test@x.com"
