"""Phase E4 — SNS client tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    from app.integrations import sns_client
    sns_client._reset_mock_topics_for_tests()
    yield


def test_publish_returns_mock_id():
    from app.integrations import sns_client
    res = sns_client.publish("donor-reply-accept", {"donor_id": "x"})
    assert res.is_mock
    assert res.message_id.startswith("MOCK-SNS-")
    assert res.topic_name.endswith("donor-reply-accept")


def test_recent_events_returns_published():
    from app.integrations import sns_client
    sns_client.publish("donor-reply-accept", {"donor_id": "x"})
    sns_client.publish("donor-reply-decline", {"donor_id": "y"})
    events = sns_client.recent_events(limit=10)
    assert len(events) == 2
    # Newest-first
    assert {e.body["donor_id"] for e in events} == {"x", "y"}


def test_recent_events_filter_by_topic():
    from app.integrations import sns_client
    sns_client.publish("donor-reply-accept", {"a": 1})
    sns_client.publish("donor-reply-decline", {"d": 1})
    accepts = sns_client.recent_events(topic_name="donor-reply-accept", limit=10)
    assert all(e.topic_name.endswith("accept") for e in accepts)
    assert len(accepts) == 1


def test_full_topic_name_prefix():
    from app.integrations import sns_client
    name = sns_client.full_topic_name("donor-reply-accept")
    assert name.startswith("team019-")
    assert name.endswith("donor-reply-accept")
