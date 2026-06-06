"""Phase E6 — SNS direct-SMS client tests.

The SMS client mirrors the SES + Twilio clients: live boto3 publish when
AWS is reachable, in-memory mock otherwise. Tests run in mock mode by
forcing BRIDGE_OS_DISABLE_AWS=1.
"""

from __future__ import annotations

import pytest

from app.integrations import sns_sms_client


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    sns_sms_client._reset_outbox_for_tests()


def test_send_sms_mock_returns_mock_id_and_records():
    r = sns_sms_client.send_sms(to_number="+919900000111", body="Test SMS")
    assert r.is_mock is True
    assert r.message_id.startswith("MOCK-SMS-")
    assert r.status == "mocked"
    assert r.error_message is None
    outbox = sns_sms_client.list_mock_sends()
    assert len(outbox) == 1
    assert outbox[0]["to"] == "+919900000111"
    assert outbox[0]["body"] == "Test SMS"


def test_send_sms_empty_recipient_fails_fast():
    r = sns_sms_client.send_sms(to_number="", body="x")
    assert r.is_mock is True
    assert r.status == "failed"
    assert r.error_message == "empty to_number"
    assert sns_sms_client.list_mock_sends() == []


def test_friendly_status_mock_mode():
    s = sns_sms_client.friendly_status()
    assert s["mode"] == "mock"
    assert s["configured"] is False


def test_multiple_sends_accumulate_in_outbox():
    sns_sms_client.send_sms(to_number="+919900000001", body="A")
    sns_sms_client.send_sms(to_number="+919900000002", body="B")
    sns_sms_client.send_sms(to_number="+919900000003", body="C")
    outbox = sns_sms_client.list_mock_sends()
    assert [s["body"] for s in outbox] == ["A", "B", "C"]
