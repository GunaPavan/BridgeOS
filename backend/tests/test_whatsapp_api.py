"""Integration tests for the /whatsapp endpoints.

Tests exercise the full request/response cycle against an in-memory SQLite
DB. Twilio is in mock mode (no env vars set), so send() returns a MOCK… SID
and writes a real DB row.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations import twilio_client
from app.models import MembershipStatus, WhatsAppMessage
from tests.fixtures import build_test_dataset, feature_bridge_destabilizer


def _seed(db_session: Session):
    return build_test_dataset(db_session, n_patients=3, n_donors=40, seed=42)


# ----- /whatsapp/status -----


def test_status_reports_mock_mode_by_default(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    body = client.get("/whatsapp/status").json()
    assert body["is_live"] is False
    assert "whatsapp:+" in body["from_number"]
    assert "join" in body["sandbox_join_instructions"].lower()


def test_status_reports_live_when_env_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token_test")
    body = client.get("/whatsapp/status").json()
    assert body["is_live"] is True


# ----- /whatsapp/templates -----


def test_templates_returns_full_set(client: TestClient) -> None:
    """G4 donor + G5 caregiver + G6 swap templates are all exposed."""
    body = client.get("/whatsapp/templates").json()
    keys = {t["key"] for t in body}
    assert {"slot_reminder", "recruit_invite", "thank_you", "swap_request"}.issubset(keys)
    for t in body:
        # Every template ships with at least en/hi/te (G6 swap templates fall
        # back to English for the other 5 languages via resolve_language()).
        assert "en" in t["supported_languages"]
        assert "hi" in t["supported_languages"]
        assert "te" in t["supported_languages"]
        # Each template's English body interpolates SOMETHING (every template
        # has at least one {variable} placeholder).
        en = t["bodies"]["en"]
        assert "{" in en and "}" in en


# ----- /whatsapp/send free-form -----


def test_send_free_form_creates_outbound_row_with_mock_sid(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    db_session.commit()
    donor = db_session.query(__import__("app.models", fromlist=["Donor"]).Donor).first()

    resp = client.post(
        "/whatsapp/send",
        json={"donor_id": str(donor.id), "body": "Hello from Bridge OS!"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_live_twilio"] is False
    msg = body["message"]
    assert msg["direction"] == "outbound"
    assert msg["body"] == "Hello from Bridge OS!"
    assert msg["twilio_sid"].startswith("MOCK")
    assert msg["status"] == "mocked"
    assert msg["to_number"] == donor.phone


def test_send_requires_body_or_template(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    db_session.commit()
    donor = db_session.query(__import__("app.models", fromlist=["Donor"]).Donor).first()
    resp = client.post(
        "/whatsapp/send", json={"donor_id": str(donor.id)}
    )
    assert resp.status_code == 400
    assert "body" in resp.json()["detail"] or "template" in resp.json()["detail"]


def test_send_unknown_donor_returns_404(client: TestClient) -> None:
    resp = client.post(
        "/whatsapp/send",
        json={"donor_id": str(uuid.uuid4()), "body": "hi"},
    )
    assert resp.status_code == 404


# ----- /whatsapp/send template -----


def test_send_template_fills_donor_and_patient_vars(
    client: TestClient, db_session: Session
) -> None:
    """G4: templates render in donor's preferred_language and substitute donor_first + patient_name."""
    data = _seed(db_session)
    db_session.commit()
    bridge = data.feature_patient.bridge  # Aarav's bridge
    donor = next(
        m.donor for m in bridge.memberships if m.status == MembershipStatus.ACTIVE
    )
    # Force English so the assertion below is language-agnostic
    from app.models import Language as _Lang
    donor.preferred_language = _Lang.ENGLISH
    db_session.commit()

    resp = client.post(
        "/whatsapp/send",
        json={
            "donor_id": str(donor.id),
            "template_key": "slot_reminder",
            "bridge_id": str(bridge.id),
            "language": "en",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    msg = body["message"]
    assert msg["template_key"] == "slot_reminder"
    # Templates use donor_first (first word of donor.name), not the full name
    donor_first = donor.name.split()[0]
    assert donor_first in msg["body"]
    assert data.feature_patient.name in msg["body"]
    assert msg["language"] == "en"


def test_send_template_requires_bridge_id_when_template_uses_patient(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    db_session.commit()
    donor = db_session.query(__import__("app.models", fromlist=["Donor"]).Donor).first()
    resp = client.post(
        "/whatsapp/send",
        json={"donor_id": str(donor.id), "template_key": "slot_reminder"},
    )
    assert resp.status_code == 400
    assert "bridge_id" in resp.json()["detail"]


def test_send_template_unknown_key_returns_400(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    db_session.commit()
    donor = db_session.query(__import__("app.models", fromlist=["Donor"]).Donor).first()
    resp = client.post(
        "/whatsapp/send",
        json={"donor_id": str(donor.id), "template_key": "nonexistent"},
    )
    assert resp.status_code == 400


# ----- /whatsapp/conversations -----


def test_conversations_empty_initially(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    db_session.commit()
    body = client.get("/whatsapp/conversations").json()
    assert body["total"] == 0
    assert body["conversations"] == []


def test_conversations_lists_donors_with_messages(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    from app.models import Donor

    d1 = db_session.query(Donor).first()
    d2 = db_session.query(Donor).offset(1).first()
    assert d1 and d2

    for body in ["First message to A", "Second message to A"]:
        client.post("/whatsapp/send", json={"donor_id": str(d1.id), "body": body})
    client.post("/whatsapp/send", json={"donor_id": str(d2.id), "body": "msg to B"})

    body = client.get("/whatsapp/conversations").json()
    assert body["total"] == 2
    by_donor = {c["donor"]["id"]: c for c in body["conversations"]}
    assert by_donor[str(d1.id)]["message_count"] == 2
    assert by_donor[str(d2.id)]["message_count"] == 1
    # Each conversation includes a last_message
    for c in body["conversations"]:
        assert c["last_message"]["direction"] == "outbound"


def test_conversations_sorted_by_most_recent(
    client: TestClient, db_session: Session
) -> None:
    """Most recently messaged donor appears first in the conversations list."""
    from datetime import datetime, timedelta

    from app.models import (
        Donor,
        MessageDirection,
        MessageStatus,
        WhatsAppMessage,
    )

    _seed(db_session)
    db_session.commit()
    donors = db_session.query(Donor).limit(3).all()
    base = datetime(2026, 5, 31, 12, 0, 0)
    for i, d in enumerate(donors):
        db_session.add(
            WhatsAppMessage(
                donor_id=d.id,
                direction=MessageDirection.OUTBOUND,
                from_number="whatsapp:+14155238886",
                to_number=d.phone,
                body=f"msg to donor {i}",
                status=MessageStatus.MOCKED,
                created_at=base + timedelta(minutes=i),
            )
        )
    db_session.commit()

    body = client.get("/whatsapp/conversations").json()
    assert [c["donor"]["id"] for c in body["conversations"]] == [
        str(donors[2].id),
        str(donors[1].id),
        str(donors[0].id),
    ]


# ----- /whatsapp/conversations/{donor_id} -----


def test_thread_returns_messages_in_chronological_order(
    client: TestClient, db_session: Session
) -> None:
    """Thread orders by created_at ascending."""
    from datetime import datetime, timedelta

    from app.models import (
        Donor,
        MessageDirection,
        MessageStatus,
        WhatsAppMessage,
    )

    _seed(db_session)
    db_session.commit()
    donor = db_session.query(Donor).first()
    bodies = ["msg one", "msg two", "msg three"]
    base = datetime(2026, 5, 31, 12, 0, 0)
    for i, b in enumerate(bodies):
        db_session.add(
            WhatsAppMessage(
                donor_id=donor.id,
                direction=MessageDirection.OUTBOUND,
                from_number="whatsapp:+14155238886",
                to_number=donor.phone,
                body=b,
                status=MessageStatus.MOCKED,
                created_at=base + timedelta(minutes=i),
            )
        )
    db_session.commit()

    body = client.get(f"/whatsapp/conversations/{donor.id}").json()
    assert body["donor"]["id"] == str(donor.id)
    assert [m["body"] for m in body["messages"]] == bodies


def test_thread_unknown_donor_returns_404(client: TestClient) -> None:
    resp = client.get(f"/whatsapp/conversations/{uuid.uuid4()}")
    assert resp.status_code == 404


# ----- /whatsapp/messages -----


def test_messages_lists_recent_across_all_donors(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    db_session.commit()
    from app.models import Donor

    for d in db_session.query(Donor).limit(5).all():
        client.post("/whatsapp/send", json={"donor_id": str(d.id), "body": "hi"})

    body = client.get("/whatsapp/messages?limit=10").json()
    assert len(body) == 5


def test_messages_respects_limit(client: TestClient, db_session: Session) -> None:
    from datetime import datetime, timedelta

    from app.models import (
        Donor,
        MessageDirection,
        MessageStatus,
        WhatsAppMessage,
    )

    _seed(db_session)
    db_session.commit()
    donor = db_session.query(Donor).first()
    base = datetime(2026, 5, 31, 12, 0, 0)
    for i in range(7):
        db_session.add(
            WhatsAppMessage(
                donor_id=donor.id,
                direction=MessageDirection.OUTBOUND,
                from_number="whatsapp:+14155238886",
                to_number=donor.phone,
                body=f"msg {i}",
                status=MessageStatus.MOCKED,
                created_at=base + timedelta(minutes=i),
            )
        )
    db_session.commit()

    body = client.get("/whatsapp/messages?limit=3").json()
    assert len(body) == 3


# ----- /whatsapp/webhook -----


def test_webhook_stores_inbound_and_returns_twiml(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    db_session.commit()
    from app.models import Donor

    donor = db_session.query(Donor).first()
    resp = client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{donor.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "YES I can donate next week",
            "MessageSid": "SM_test_inbound_001",
        },
    )
    assert resp.status_code == 200
    assert "<Response>" in resp.text
    assert "<Message>" in resp.text
    # Inbound row recorded against donor
    inbound = (
        db_session.query(WhatsAppMessage)
        .filter(WhatsAppMessage.direction == "inbound")
        .one()
    )
    assert inbound.donor_id == donor.id
    assert inbound.body == "YES I can donate next week"
    assert inbound.twilio_sid == "SM_test_inbound_001"


def test_webhook_with_unknown_sender_still_stores_message(
    client: TestClient, db_session: Session
) -> None:
    """Twilio sends inbound for any opted-in number — we should not 404 it."""
    resp = client.post(
        "/whatsapp/webhook",
        data={
            "From": "whatsapp:+15551234567",
            "To": twilio_client.whatsapp_from(),
            "Body": "Random message",
            "MessageSid": "SM_unknown",
        },
    )
    assert resp.status_code == 200
    inbound = (
        db_session.query(WhatsAppMessage)
        .filter(WhatsAppMessage.body == "Random message")
        .one()
    )
    assert inbound.donor_id is None
    assert inbound.body == "Random message"


# ----- twilio_client unit-ish tests -----


def test_twilio_client_mock_mode_returns_mock_sid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    assert twilio_client.is_live() is False
    result = twilio_client.send_whatsapp("+919900000001", "test")
    assert result.is_mock is True
    assert result.sid.startswith("MOCK")
    assert result.status == "mocked"


def test_twilio_client_is_live_requires_both_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_only")
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    assert twilio_client.is_live() is False
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    assert twilio_client.is_live() is True


def test_twilio_from_number_default_is_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWILIO_WHATSAPP_FROM", raising=False)
    assert twilio_client.whatsapp_from() == "whatsapp:+14155238886"


def test_twilio_from_number_uses_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+919900000099")
    assert twilio_client.whatsapp_from() == "whatsapp:+919900000099"
