"""AWS SES client with built-in mock fallback.

When `AWS_ACCESS_KEY_ID` is set (or any of the auth chain) the client uses
boto3 to send mail through SES. Otherwise it operates in mock mode, returning
a fake message id so the rest of the system (storage, UI, demo) works without
any cloud configuration.

To enable live SES (sandbox):
    1. Sign in to the AWS Console → SES (us-east-1)
    2. Identities → Create identity → Email address → enter the address
    3. Click the verify link in the email AWS sends
    4. Set env var SES_FROM_EMAIL to that verified address
    5. Restart uvicorn — outbound emails now ship for real

Sandbox limitations: SES Sandbox sends only to verified recipients. Both
sender + recipient must be verified. Once verified, all flows work end-to-end.

Mirror of ``app.integrations.twilio_client`` — same dataclass shape, same
mock-mode behaviour.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass

from app.integrations.aws import aws_available, get_boto3_client, get_region

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SendResult:
    message_id: str
    is_mock: bool
    status: str  # "sent" | "mocked" | "failed"
    error_message: str | None = None


def _env(name: str) -> str | None:
    val = os.environ.get(name)
    return val if val else None


def is_live() -> bool:
    """True if SES creds are configured AND a from-address is set."""
    return aws_available() and bool(_env("SES_FROM_EMAIL"))


def from_email() -> str:
    """The verified 'From' address. Defaults to a sandbox placeholder."""
    return _env("SES_FROM_EMAIL") or "no-reply@bridgeos.example"


def send_email(*, to: str, subject: str, body: str) -> SendResult:
    """Send an email via SES, or a mock message id if not configured.

    Always returns a SendResult — never raises on transport errors. Caller
    inspects ``result.status`` + ``result.error_message`` for failure detail.
    """
    if not to or not to.strip():
        return SendResult(
            message_id="EMPTY-" + secrets.token_hex(8).upper(),
            is_mock=True,
            status="failed",
            error_message="empty recipient",
        )

    if not is_live():
        mid = "MOCK-EMAIL-" + secrets.token_hex(8).upper()
        return SendResult(message_id=mid, is_mock=True, status="mocked")

    sender = from_email()
    try:
        client = get_boto3_client("ses", region=get_region())
        resp = client.send_email(
            Source=sender,
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
        return SendResult(
            message_id=resp.get("MessageId", "UNKNOWN"),
            is_mock=False,
            status="sent",
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.exception("SES send failed to %s", to)
        return SendResult(
            message_id="FAIL-" + secrets.token_hex(8).upper(),
            is_mock=False,
            status="failed",
            error_message=str(exc)[:300],
        )


# ---------------------------------------------------------------------------
# Identity verification (helpers for ops scripts — not called from the app)
# ---------------------------------------------------------------------------


def verify_email_identity(email: str) -> dict:
    """Send the SES sandbox verification mail to ``email``.

    Useful from a one-shot script (``scripts/ses_verify_identity.py``).
    """
    if not aws_available():
        return {"ok": False, "mode": "mock", "note": "AWS creds not available"}
    try:
        client = get_boto3_client("ses", region=get_region())
        client.verify_email_identity(EmailAddress=email)
        return {"ok": True, "mode": "live", "email": email}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "mode": "live", "error": str(exc)[:300]}


def list_verified_identities() -> dict:
    """Return SES verified identities — used by the /system/health/full
    expansion later, and by ops scripts."""
    if not aws_available():
        return {"identities": [], "mode": "mock"}
    try:
        client = get_boto3_client("ses", region=get_region())
        resp = client.list_identities(IdentityType="EmailAddress")
        return {
            "identities": resp.get("Identities", []),
            "mode": "live",
        }
    except Exception as exc:  # pragma: no cover
        return {"identities": [], "mode": "live", "error": str(exc)[:300]}
