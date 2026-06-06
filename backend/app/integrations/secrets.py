"""Secrets Manager loader.

When ``BRIDGE_OS_USE_SECRETS_MANAGER=1`` is set, the app pulls config from
3 Secrets Manager secrets at boot and stuffs the values back into the
process environment so the rest of the code (twilio_client, ses_client,
db.py, etc.) keeps reading from ``os.environ`` like it always did.

  bridge-os/twilio      → TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
  bridge-os/database    → DB_USERNAME, DB_PASSWORD, DB_NAME, DB_PORT (+ DB_HOST set
                          by App Runner env so we get DATABASE_URL)
  bridge-os/app-config  → SES_FROM_EMAIL, BEDROCK_REGION, BRIDGE_OS_AWS_PREFIX

Local dev (no env var set) → no-op. Existing .env / env vars / hard-coded
defaults all keep working.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.environ.get("BRIDGE_OS_USE_SECRETS_MANAGER", "").lower() in ("1", "true", "yes")


def _fetch(secret_name: str, region: str) -> Optional[dict]:
    try:
        import boto3  # lazy import — local dev shouldn't pay this
    except ImportError:
        logger.warning("boto3 not installed — cannot read %s", secret_name)
        return None
    try:
        client = boto3.client("secretsmanager", region_name=region)
        resp = client.get_secret_value(SecretId=secret_name)
        return json.loads(resp["SecretString"])
    except Exception as exc:
        logger.warning("Failed to read secret %s: %s", secret_name, exc)
        return None


def _apply(d: Optional[dict]) -> int:
    """Push secret keys into os.environ ONLY if not already set (env var wins)."""
    if not d:
        return 0
    n = 0
    for k, v in d.items():
        if k not in os.environ:
            os.environ[k] = str(v)
            n += 1
    return n


def load_secrets_into_env() -> None:
    """Idempotent loader called from app.main:create_app."""
    if not _enabled():
        return
    region = os.environ.get("AWS_REGION") or os.environ.get("BEDROCK_REGION") or "us-east-1"
    total = 0
    for name in ("bridge-os/twilio", "bridge-os/database", "bridge-os/app-config"):
        total += _apply(_fetch(name, region))

    # Compose DATABASE_URL if we have parts but no full URL
    if "DATABASE_URL" not in os.environ:
        host = os.environ.get("DB_HOST")
        user = os.environ.get("DB_USERNAME")
        password = os.environ.get("DB_PASSWORD")
        name = os.environ.get("DB_NAME", "bridgeos")
        port = os.environ.get("DB_PORT", "5432")
        if host and user and password:
            os.environ["DATABASE_URL"] = (
                f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"
            )
            total += 1

    logger.info("Secrets Manager: loaded %d env vars", total)
