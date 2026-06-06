"""AWS SNS direct-SMS client with in-memory mock fallback.

Different API path from the SNS *topic* publish we use for the event bus —
this one calls ``sns.publish(PhoneNumber=...)`` and AWS routes the message
to the carrier as a real SMS.

WHY SMS FIRST
-------------
For tier-2/3 India (the Blood Warriors target audience) SMS hits 100% of
phones — no app install, no data plan, no WhatsApp opt-in needed. Older
Android phones, kaios feature phones, and zero-data devices all receive
SMS. WhatsApp drops you to ~80% reach. Email is caregiver-only.

So default donor channel = SMS.

ONE-WAY CAVEAT
--------------
SNS direct-SMS is **outbound only**. Donor replies to an SMS do NOT come
back through SNS — they vanish unless we have DLT-registered numbers
(India) or 10DLC (US), which take weeks to provision. For now:

  - Outbound: SMS (this module) / WhatsApp (Twilio) / Email (SES)
  - Inbound: only Twilio WhatsApp webhook

When an SMS-only donor wants to reply, the UI surfaces a "call coordinator"
prompt in the SMS body.

MOCK MODE
---------
When AWS isn't reachable, ``send_sms`` returns a ``MOCK-SMS-{hex}`` id and
records the call in an in-process list so tests + dev can assert without
hitting AWS.
"""

from __future__ import annotations

import logging
import secrets
import threading
from dataclasses import dataclass, field
from typing import Optional

from app.integrations.aws import (
    aws_available,
    get_boto3_client,
    get_region,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SmsSendResult:
    """Mirror of TwilioSendResult / SESSendResult dataclasses so callers can
    treat all three channels uniformly."""

    message_id: str
    is_mock: bool
    status: str  # 'sent' | 'mocked' | 'failed'
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Mock backend
# ---------------------------------------------------------------------------


@dataclass
class _MockOutbox:
    sent: list[dict] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


_OUTBOX = _MockOutbox()


def _reset_outbox_for_tests() -> None:
    with _OUTBOX.lock:
        _OUTBOX.sent.clear()


def list_mock_sends() -> list[dict]:
    """Return the in-process outbox — used by tests + the dev /system feed."""
    with _OUTBOX.lock:
        return list(_OUTBOX.sent)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def send_sms(*, to_number: str, body: str) -> SmsSendResult:
    """Send a single SMS to a phone number via SNS direct-SMS.

    ``to_number`` must be E.164 (e.g. ``+919900000123``). SNS rejects
    bare 10-digit Indian numbers.

    Falls back to mock mode when AWS isn't reachable. Mock-mode results
    look identical at the call site — same dataclass, same `is_mock` flag
    so the dispatcher can record them in the right column.
    """
    if not to_number:
        return SmsSendResult(
            message_id="",
            is_mock=True,
            status="failed",
            error_message="empty to_number",
        )

    if not aws_available():
        mid = "MOCK-SMS-" + secrets.token_hex(8).upper()
        with _OUTBOX.lock:
            _OUTBOX.sent.append(
                {"message_id": mid, "to": to_number, "body": body, "mock": True}
            )
        return SmsSendResult(message_id=mid, is_mock=True, status="mocked")

    try:
        client = get_boto3_client("sns", region=get_region())
        # Optional sender attributes: pin the SMS type to "Transactional" so
        # carriers don't down-prioritise — Blood Bridge alerts are critical.
        attributes = {
            "AWS.SNS.SMS.SMSType": {
                "DataType": "String",
                "StringValue": "Transactional",
            },
            "AWS.SNS.SMS.SenderID": {
                "DataType": "String",
                "StringValue": "BLDWAR",  # 6-char alphanumeric sender id
            },
        }
        resp = client.publish(
            PhoneNumber=to_number,
            Message=body,
            MessageAttributes=attributes,
        )
        return SmsSendResult(
            message_id=resp.get("MessageId", "UNKNOWN"),
            is_mock=False,
            status="sent",
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("SNS direct-SMS failed to %s", to_number)
        return SmsSendResult(
            message_id="FAIL-" + secrets.token_hex(8).upper(),
            is_mock=False,
            status="failed",
            error_message=str(exc)[:300],
        )


def friendly_status() -> dict:
    """Health probe — exposed via /system/health/full for the SMS channel."""
    if not aws_available():
        return {"configured": False, "mode": "mock", "region": get_region()}
    return {
        "configured": True,
        "mode": "live",
        "region": get_region(),
        "sender_id": "BLDWAR",
        "note": (
            "Outbound only — donor replies do NOT come back to SNS. "
            "Inbound replies require Twilio WhatsApp or DLT-registered numbers."
        ),
    }
