"""Phase E1 — AWS bootstrap layer tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_get_region_default(monkeypatch):
    for v in ("AWS_REGION", "AWS_DEFAULT_REGION", "BEDROCK_REGION"):
        monkeypatch.delenv(v, raising=False)
    from app.integrations.aws import get_region
    assert get_region() == "us-east-1"


def test_get_region_env_override(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    from app.integrations.aws import get_region
    assert get_region() == "eu-west-1"


def test_get_region_falls_back_to_bedrock_region(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.setenv("BEDROCK_REGION", "ap-south-1")
    from app.integrations.aws import get_region
    assert get_region() == "ap-south-1"


def test_aws_available_with_env_keys(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA-test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret-test")
    monkeypatch.delenv("BRIDGE_OS_DISABLE_AWS", raising=False)
    from app.integrations.aws import aws_available
    assert aws_available() is True


def test_aws_available_with_profile(monkeypatch):
    for v in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("AWS_PROFILE", "team019")
    from app.integrations.aws import aws_available
    assert aws_available() is True


def test_aws_available_disabled_flag(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA-test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret-test")
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    from app.integrations.aws import aws_available
    assert aws_available() is False


def test_friendly_status_shape(monkeypatch):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_PROFILE", raising=False)
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    from app.integrations.aws import friendly_status

    fs = friendly_status("ses", resource="test@example.com")
    assert fs["configured"] is False
    assert fs["mode"] == "mock"
    assert fs["region"]
    assert fs["resource"] == "test@example.com"
    assert "mock" in (fs["note"] or "").lower()


def test_resource_prefix_default():
    from app.integrations.aws import resource_prefix
    assert resource_prefix().startswith("team019-")


def test_resource_prefix_env_override(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_AWS_PREFIX", "team099-test")
    from app.integrations.aws import resource_prefix
    assert resource_prefix() == "team099-test"


def test_resource_tags_have_required_keys():
    from app.integrations.aws import resource_tags
    tags = resource_tags()
    keys = {t["Key"] for t in tags}
    assert {"Project", "Team", "Owner"}.issubset(keys)


def test_get_boto3_client_caches(monkeypatch):
    """Same service → same client instance (lru_cache)."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA-test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret-test")
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    from app.integrations import aws

    # Clear the lru_cache before we test
    aws.get_boto3_client.cache_clear()

    c1 = aws.get_boto3_client("sqs")
    c2 = aws.get_boto3_client("sqs")
    assert c1 is c2


def test_full_health_includes_ses_sqs_sns(client) -> None:
    r = client.get("/system/health/full")
    assert r.status_code == 200
    body = r.json()
    for key in ("ses", "sqs", "sns"):
        assert key in body
        assert "configured" in body[key]
        assert "mode" in body[key]
        assert "region" in body[key]
