"""Phase E4 — confirm the WhatsApp webhook publishes to SNS topics.

End-to-end: a donor sends an inbound message that the smart classifier
labels as OUT_OF_TOWN / MEDICAL_DEFER / STOP. The webhook publishes the
classified intent onto the matching SNS topic so audit subscribers
(cooldown, EMA) can fan out.

These tests stub the LLM classifier so we don't hit Bedrock.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations import sns_client
from app.models import (
    BloodGroup,
    Donor,
    Language,
    ReplyIntent,
)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    sns_client._reset_mock_topics_for_tests()
    # Touch subscribers so the registry is populated
    from app.events import subscribers  # noqa: F401


def _make_donor(db_session: Session, *, phone: str = "+919900000111") -> Donor:
    d = Donor(
        name="Test Donor",
        age=28,
        phone=phone,
        blood_group=BloodGroup.B_POS,
        city="Hyderabad",
        state="Telangana",
        lat=17.39,
        lng=78.46,
        preferred_language=Language.ENGLISH,
        is_active=True,
    )
    db_session.add(d)
    db_session.flush()
    return d


def _classification(intent: ReplyIntent, confidence: float = 0.95):
    """Mimic the ClassifiedReply dataclass shape consumed by the webhook."""
    from app.services.reply_classifier import ClassifiedReply

    return ClassifiedReply(
        intent=intent,
        confidence=confidence,
        extracted_date=None,
        extracted_reason=None,
        model_used="mock",
        raw_response="",
        used_fallback=False,
    )


def _published_topics() -> list[str]:
    """Return a list of full topic names that received at least one publish."""
    events = sns_client.recent_events(limit=200)
    return sorted({e.topic_name for e in events})


def test_webhook_publishes_out_of_town(client: TestClient, db_session: Session):
    donor = _make_donor(db_session, phone="+919900000201")
    db_session.commit()

    with patch(
        "app.services.reply_classifier.classify_reply",
        return_value=_classification(ReplyIntent.OUT_OF_TOWN),
    ):
        r = client.post(
            "/whatsapp/webhook",
            data={
                "From": f"whatsapp:{donor.phone}",
                "To": "whatsapp:+14155238886",
                "Body": "Out of town for the next week, can't make it",
                "MessageSid": "SM-test-out-of-town",
            },
        )
    assert r.status_code == 200
    topics = _published_topics()
    assert any(t.endswith("donor-reply-out-of-town") for t in topics), (
        f"expected donor-reply-out-of-town in {topics}"
    )


def test_webhook_publishes_medical_defer(client: TestClient, db_session: Session):
    donor = _make_donor(db_session, phone="+919900000202")
    db_session.commit()

    with patch(
        "app.services.reply_classifier.classify_reply",
        return_value=_classification(ReplyIntent.MEDICAL_DEFER),
    ):
        r = client.post(
            "/whatsapp/webhook",
            data={
                "From": f"whatsapp:{donor.phone}",
                "To": "whatsapp:+14155238886",
                "Body": "I had a fever last week, doctor said wait 2 weeks",
                "MessageSid": "SM-test-medical-defer",
            },
        )
    assert r.status_code == 200
    topics = _published_topics()
    assert any(t.endswith("donor-reply-medical-defer") for t in topics), (
        f"expected donor-reply-medical-defer in {topics}"
    )


def test_webhook_publishes_opt_out(client: TestClient, db_session: Session):
    donor = _make_donor(db_session, phone="+919900000203")
    db_session.commit()

    with patch(
        "app.services.reply_classifier.classify_reply",
        return_value=_classification(ReplyIntent.STOP),
    ):
        r = client.post(
            "/whatsapp/webhook",
            data={
                "From": f"whatsapp:{donor.phone}",
                "To": "whatsapp:+14155238886",
                "Body": "STOP",
                "MessageSid": "SM-test-stop",
            },
        )
    assert r.status_code == 200
    topics = _published_topics()
    assert any(t.endswith("donor-reply-opt-out") for t in topics), (
        f"expected donor-reply-opt-out in {topics}"
    )


def test_webhook_does_not_publish_on_low_confidence(
    client: TestClient, db_session: Session
):
    """If the classifier confidence falls below the actionable threshold,
    the webhook should fall through to the legacy keyword path and not
    publish anything."""
    donor = _make_donor(db_session, phone="+919900000204")
    db_session.commit()

    with patch(
        "app.services.reply_classifier.classify_reply",
        return_value=_classification(ReplyIntent.OUT_OF_TOWN, confidence=0.2),
    ):
        r = client.post(
            "/whatsapp/webhook",
            data={
                "From": f"whatsapp:{donor.phone}",
                "To": "whatsapp:+14155238886",
                "Body": "hmm",
                "MessageSid": "SM-test-low-conf",
            },
        )
    assert r.status_code == 200
    # No donor-reply-* topic should have been published
    topics = _published_topics()
    assert not any("donor-reply-" in t for t in topics), (
        f"unexpected publish: {topics}"
    )
