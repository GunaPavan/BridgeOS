"""Phase E4 — typed publish helper tests."""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    from app.integrations import sns_client
    sns_client._reset_mock_topics_for_tests()
    yield


def test_publish_donor_reply_accept_writes_history():
    from app.events.publishers import publish_donor_reply_accept
    from app.integrations import sns_client

    mid = publish_donor_reply_accept(donor_id=uuid.uuid4(), ping_id=uuid.uuid4())
    assert mid.startswith("MOCK-SNS-")
    events = sns_client.recent_events()
    assert len(events) == 1
    assert events[0].body["donor_id"]


def test_publish_donor_reply_out_of_town():
    from app.events.publishers import publish_donor_reply_out_of_town
    from app.integrations import sns_client

    publish_donor_reply_out_of_town(donor_id=uuid.uuid4())
    events = sns_client.recent_events()
    assert events[0].topic_name.endswith("donor-reply-out-of-town")


def test_publish_donor_reply_medical_defer_carries_reason():
    from app.events.publishers import publish_donor_reply_medical_defer
    from app.integrations import sns_client

    publish_donor_reply_medical_defer(donor_id=uuid.uuid4(), reason="fever")
    events = sns_client.recent_events()
    assert events[0].body["reason"] == "fever"


def test_publish_wave_expired():
    from app.events.publishers import publish_wave_expired
    from app.integrations import sns_client

    publish_wave_expired(wave_id=uuid.uuid4(), tier="tier_2")
    events = sns_client.recent_events()
    assert events[0].body["tier"] == "tier_2"
