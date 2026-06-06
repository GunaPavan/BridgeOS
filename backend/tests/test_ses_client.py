"""Phase E2 — SES client tests (mock + live paths)."""

from __future__ import annotations

import pytest

from app.integrations import ses_client


def test_mock_send_returns_mock_id(monkeypatch):
    """No AWS creds → returns MOCK-EMAIL-...; never raises."""
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    monkeypatch.delenv("SES_FROM_EMAIL", raising=False)
    result = ses_client.send_email(
        to="caregiver@example.com",
        subject="Test",
        body="Hi",
    )
    assert result.is_mock
    assert result.status == "mocked"
    assert result.message_id.startswith("MOCK-EMAIL-")


def test_empty_recipient_returns_failed(monkeypatch):
    result = ses_client.send_email(to="", subject="x", body="y")
    assert result.status == "failed"
    assert "empty" in (result.error_message or "").lower()


def test_is_live_requires_both_aws_and_from_email(monkeypatch):
    monkeypatch.delenv("BRIDGE_OS_DISABLE_AWS", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")
    monkeypatch.delenv("SES_FROM_EMAIL", raising=False)
    assert ses_client.is_live() is False  # missing SES_FROM_EMAIL

    monkeypatch.setenv("SES_FROM_EMAIL", "ops@team019.example")
    assert ses_client.is_live() is True


def test_from_email_default(monkeypatch):
    monkeypatch.delenv("SES_FROM_EMAIL", raising=False)
    assert "@" in ses_client.from_email()


def test_live_path_calls_boto3(monkeypatch):
    """When configured, ses_client.send_email calls ses.send_email and returns
    the MessageId from the response."""
    monkeypatch.delenv("BRIDGE_OS_DISABLE_AWS", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")
    monkeypatch.setenv("SES_FROM_EMAIL", "ops@team019.example")

    calls = []

    class _FakeSESClient:
        def send_email(self, **kwargs):
            calls.append(kwargs)
            return {"MessageId": "real-ses-id-123"}

    # Patch get_boto3_client to return our fake
    monkeypatch.setattr(
        "app.integrations.ses_client.get_boto3_client",
        lambda service, region=None: _FakeSESClient(),
    )

    result = ses_client.send_email(
        to="caregiver@example.com", subject="hello", body="text"
    )
    assert result.is_mock is False
    assert result.status == "sent"
    assert result.message_id == "real-ses-id-123"
    assert calls[0]["Source"] == "ops@team019.example"
    assert calls[0]["Destination"]["ToAddresses"] == ["caregiver@example.com"]


def test_live_path_catches_exceptions(monkeypatch):
    monkeypatch.delenv("BRIDGE_OS_DISABLE_AWS", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")
    monkeypatch.setenv("SES_FROM_EMAIL", "ops@team019.example")

    class _Boom:
        def send_email(self, **kwargs):
            raise RuntimeError("AWS exploded")

    monkeypatch.setattr(
        "app.integrations.ses_client.get_boto3_client",
        lambda service, region=None: _Boom(),
    )
    result = ses_client.send_email(to="x@y.z", subject="x", body="y")
    assert result.status == "failed"
    assert "exploded" in (result.error_message or "")
