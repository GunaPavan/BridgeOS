"""E10 — Secrets Manager loader tests."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.integrations import secrets


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip any env vars we test so each run starts clean."""
    for k in (
        "BRIDGE_OS_USE_SECRETS_MANAGER",
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
        "DB_USERNAME", "DB_PASSWORD", "DB_NAME", "DB_PORT", "DB_HOST",
        "SES_FROM_EMAIL", "BEDROCK_REGION", "BRIDGE_OS_AWS_PREFIX",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(k, raising=False)


def test_disabled_when_env_var_not_set():
    """Without BRIDGE_OS_USE_SECRETS_MANAGER, the loader is a no-op."""
    # _fetch shouldn't even get called
    with patch.object(secrets, "_fetch") as fetcher:
        secrets.load_secrets_into_env()
        fetcher.assert_not_called()


def test_loads_three_secrets_when_enabled(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_USE_SECRETS_MANAGER", "1")

    fake = {
        "bridge-os/twilio": {
            "TWILIO_ACCOUNT_SID": "AC123",
            "TWILIO_AUTH_TOKEN": "tok",
        },
        "bridge-os/database": {
            "DB_USERNAME": "bridgeos",
            "DB_PASSWORD": "supersecret",
            "DB_NAME": "bridgeos",
            "DB_PORT": "5432",
        },
        "bridge-os/app-config": {
            "SES_FROM_EMAIL": "ops@bridge-os.click",
            "BEDROCK_REGION": "us-east-1",
        },
    }

    def _fake_fetch(name, region):
        return fake.get(name)

    with patch.object(secrets, "_fetch", side_effect=_fake_fetch):
        secrets.load_secrets_into_env()

    assert os.environ.get("TWILIO_ACCOUNT_SID") == "AC123"
    assert os.environ.get("DB_PASSWORD") == "supersecret"
    assert os.environ.get("SES_FROM_EMAIL") == "ops@bridge-os.click"


def test_existing_env_vars_take_precedence(monkeypatch):
    """If DATABASE_URL is already set, the loader doesn't overwrite."""
    monkeypatch.setenv("BRIDGE_OS_USE_SECRETS_MANAGER", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://override:5432/x")

    def _fake_fetch(name, region):
        return {"DATABASE_URL": "should-not-win"} if name == "bridge-os/database" else None

    with patch.object(secrets, "_fetch", side_effect=_fake_fetch):
        secrets.load_secrets_into_env()

    assert os.environ["DATABASE_URL"] == "postgresql://override:5432/x"


def test_composes_database_url_from_parts(monkeypatch):
    """When DB_HOST is supplied (App Runner env) + creds from Secrets,
    the loader builds a full DATABASE_URL."""
    monkeypatch.setenv("BRIDGE_OS_USE_SECRETS_MANAGER", "1")
    monkeypatch.setenv("DB_HOST", "team019-bridge-os-pg.us-east-1.rds.amazonaws.com")

    def _fake_fetch(name, region):
        if name == "bridge-os/database":
            return {"DB_USERNAME": "bridgeos", "DB_PASSWORD": "pw", "DB_NAME": "bridgeos", "DB_PORT": "5432"}
        return None

    with patch.object(secrets, "_fetch", side_effect=_fake_fetch):
        secrets.load_secrets_into_env()

    url = os.environ.get("DATABASE_URL", "")
    assert url.startswith("postgresql+psycopg://bridgeos:pw@team019-bridge-os-pg")
    assert url.endswith(":5432/bridgeos")
