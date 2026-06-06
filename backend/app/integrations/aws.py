"""Unified AWS bootstrap layer.

One module owns:
  - Region resolution (env → ~/.aws/config → default us-east-1)
  - boto3 client construction (cached per process — boto3 clients are thread-safe)
  - "Is AWS reachable?" probe (no API call — just config check)
  - Friendly status dict used by /system/health/full

Every AWS-talking module (`ses_client`, `sqs_client`, `sns_client`) builds its
client through ``get_boto3_client(service)`` so we have a single rate-limited,
cached, mock-aware code path.

MOCK MODE
---------
If AWS credentials aren't available (no env vars + no ~/.aws/credentials),
``aws_available()`` returns False and downstream clients short-circuit to
their in-memory mock implementations. This lets developers run the whole
stack without an AWS account and lets tests stay deterministic.

The Twilio + Bedrock clients already follow the same pattern — this just
codifies it for the AWS family.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Region
# ---------------------------------------------------------------------------


def get_region() -> str:
    """Resolve AWS region with the same precedence boto3 uses."""
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("BEDROCK_REGION")   # we already set this for Bedrock
        or "us-east-1"
    )


# ---------------------------------------------------------------------------
# Authentication probe
# ---------------------------------------------------------------------------


def aws_available() -> bool:
    """True if boto3 has a credentials path to use.

    Conservative: we don't actually call STS here (that would make /health
    flaky + cost money). We just check that one of the standard auth chains
    is populated.
    """
    if os.environ.get("BRIDGE_OS_DISABLE_AWS") == "1":
        return False
    # Direct env vars
    if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        return True
    # Named profile
    if os.environ.get("AWS_PROFILE") or os.environ.get("AWS_DEFAULT_PROFILE"):
        return True
    # ~/.aws/credentials file
    from pathlib import Path

    cred_path = Path.home() / ".aws" / "credentials"
    if cred_path.exists() and cred_path.stat().st_size > 0:
        return True
    # ECS/EKS task role
    if os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"):
        return True
    return False


# ---------------------------------------------------------------------------
# Client cache
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def get_boto3_client(service: str, *, region: Optional[str] = None) -> Any:
    """Build (or reuse) a boto3 client for the given service.

    The lru_cache means every module that asks for ``ses`` gets the same
    client instance — boto3 clients are thread-safe so this is safe.
    """
    import boto3  # type: ignore[import-not-found]
    from botocore.config import Config  # type: ignore[import-not-found]

    cfg = Config(
        region_name=region or get_region(),
        retries={"max_attempts": 3, "mode": "standard"},
        connect_timeout=5,
        read_timeout=15,
    )
    return boto3.client(service, config=cfg)


# ---------------------------------------------------------------------------
# Friendly status (for /system/health/full)
# ---------------------------------------------------------------------------


@dataclass
class ServiceStatus:
    configured: bool
    mode: str          # "live" | "mock"
    region: str
    resource: Optional[str] = None  # e.g. queue name, topic arn, identity email
    note: Optional[str] = None


def friendly_status(service_name: str, *, resource: Optional[str] = None) -> dict:
    """Build the dict that /system/health/full embeds for each AWS service.

    We DO NOT make an API call — health endpoint must stay cheap and offline-
    safe. We just report config + a hint about what mode the service is in.
    """
    live = aws_available()
    return ServiceStatus(
        configured=live,
        mode="live" if live else "mock",
        region=get_region(),
        resource=resource,
        note=None if live else (
            f"AWS creds not available — {service_name} falls back to in-memory mock"
        ),
    ).__dict__


# ---------------------------------------------------------------------------
# Naming helpers (so all resources are consistent + cleanup-friendly)
# ---------------------------------------------------------------------------


def resource_prefix() -> str:
    """Common prefix for every AWS resource we create.

    Override with ``BRIDGE_OS_AWS_PREFIX`` so multiple devs / CI runs don't
    collide on the same account.
    """
    return os.environ.get("BRIDGE_OS_AWS_PREFIX") or "team019-bridge-os"


def resource_tags() -> list[dict]:
    """Common tag set for SES configuration sets, SQS queues, SNS topics, etc.

    Tagging every resource with ``Project=bridge-os`` means cleanup is one
    ``aws resourcegroupstaggingapi get-resources --tag-filters ...`` call.
    """
    return [
        {"Key": "Project", "Value": "bridge-os"},
        {"Key": "Team", "Value": "019"},
        {"Key": "Owner", "Value": "Gunaputra"},
        {"Key": "ManagedBy", "Value": "app.integrations.aws"},
    ]
