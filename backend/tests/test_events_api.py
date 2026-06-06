"""Phase E4 — /system/events/* endpoint tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    from app.integrations import sns_client
    sns_client._reset_mock_topics_for_tests()
    # Touch subscribers so the registry has entries
    from app.events import subscribers  # noqa: F401
    yield


def test_topics_endpoint_lists_all_with_subscribers(client: TestClient):
    r = client.get("/system/events/topics")
    assert r.status_code == 200
    body = r.json()
    topics = {t["topic"] for t in body}
    assert "donor-reply-accept" in topics
    assert "wave-expired" in topics
    # The out-of-town topic has at least one subscriber registered
    out_of_town = next(t for t in body if t["topic"] == "donor-reply-out-of-town")
    assert len(out_of_town["subscribers"]) >= 1


def test_recent_endpoint_returns_published_events(client: TestClient):
    from app.events.publishers import publish_donor_reply_accept
    import uuid

    publish_donor_reply_accept(donor_id=uuid.uuid4())
    r = client.get("/system/events/recent?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 1
    assert body[0]["topic_name"].endswith("donor-reply-accept")


def test_recent_endpoint_topic_filter(client: TestClient):
    from app.events.publishers import (
        publish_donor_reply_accept,
        publish_donor_reply_decline,
    )
    import uuid

    publish_donor_reply_accept(donor_id=uuid.uuid4())
    publish_donor_reply_decline(donor_id=uuid.uuid4())

    r = client.get("/system/events/recent?topic=donor-reply-accept&limit=10")
    body = r.json()
    assert len(body) == 1
    assert body[0]["topic_name"].endswith("donor-reply-accept")


def test_dispatcher_status_shape(client: TestClient):
    r = client.get("/system/events/status")
    assert r.status_code == 200
    body = r.json()
    for key in ("running", "delivered", "failed", "topics"):
        assert key in body


def test_republish_event_creates_new_message(client: TestClient):
    from app.events.publishers import publish_donor_reply_accept
    import uuid

    original_mid = publish_donor_reply_accept(donor_id=uuid.uuid4())
    r = client.post(f"/system/events/republish/{original_mid}")
    assert r.status_code == 200
    body = r.json()
    assert body["original_message_id"] == original_mid
    assert body["new_message_id"] != original_mid
    assert body["topic_name"].endswith("donor-reply-accept")


def test_republish_event_404_when_missing(client: TestClient):
    r = client.post("/system/events/republish/does-not-exist")
    assert r.status_code == 404
