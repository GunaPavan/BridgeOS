"""Twilio WhatsApp client with a built-in mock fallback.

When `TWILIO_ACCOUNT_SID` is set the client uses the real `twilio` Python SDK
to send messages. Otherwise it operates in mock mode, returning a fake SID
so the rest of the system (storage, UI, demo) works without any cloud
configuration.

To enable the live Twilio Sandbox:
    1. Sign up at https://www.twilio.com/console (free trial)
    2. Activate the WhatsApp Sandbox (Settings → Programmable Messaging)
    3. Set env vars:
         TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
    4. Donors send the sandbox join code to the sandbox number to opt in.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class SendResult:
    sid: str
    is_mock: bool
    status: str  # e.g. "queued", "mocked"


def _env(name: str) -> str | None:
    val = os.environ.get(name)
    return val if val else None


def is_live() -> bool:
    """True if Twilio creds are configured."""
    return _env("TWILIO_ACCOUNT_SID") is not None and _env("TWILIO_AUTH_TOKEN") is not None


def whatsapp_from() -> str:
    """The 'From' WhatsApp number (defaults to Twilio's sandbox number)."""
    return _env("TWILIO_WHATSAPP_FROM") or "whatsapp:+14155238886"


def send_whatsapp(to_number: str, body: str) -> SendResult:
    """Send a WhatsApp message via Twilio, or a mock SID if not configured."""
    if not is_live():
        sid = "MOCK" + secrets.token_hex(16).upper()
        return SendResult(sid=sid, is_mock=True, status="mocked")

    # Lazy import so the SDK isn't required for mock mode
    from twilio.rest import Client  # type: ignore[import-not-found]

    sid_env = _env("TWILIO_ACCOUNT_SID")
    auth_env = _env("TWILIO_AUTH_TOKEN")
    assert sid_env and auth_env, "twilio creds required when is_live()"
    client = Client(sid_env, auth_env)
    msg = client.messages.create(
        from_=whatsapp_from(),
        to=to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}",
        body=body,
    )
    return SendResult(sid=msg.sid, is_mock=False, status=msg.status or "queued")
