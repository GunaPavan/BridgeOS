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
from typing import Optional


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


def voice_from() -> str:
    """The phone number Twilio uses to place outbound voice calls.

    Different from the WhatsApp sandbox 'from' — voice needs a real
    Twilio-purchased number. In trial mode this is the user's Twilio
    trial number (set via TWILIO_VOICE_FROM).
    """
    return _env("TWILIO_VOICE_FROM") or "+13853786738"  # default to user's trial


def place_voice_call(
    *,
    to_number: str,
    message: str,
    twiml_url: Optional[str] = None,
    ping_id: Optional[str] = None,
) -> SendResult:
    """Place an outbound voice call.

    Two modes:

      (a) ``twiml_url`` provided — Twilio fetches the TwiML from that URL
          when the call connects. This is the bidirectional path: the URL
          points at ``/twilio/voice/twiml/ask`` which plays the question +
          opens a ``<Gather speech>`` so the donor can answer.

      (b) ``twiml_url`` omitted — fall back to inline TwiML that just
          reads ``message`` twice and hangs up (one-way alert mode, used
          for coordinator escalations).

    Mock mode returns ``MOCK-CALL-...`` SIDs in both cases.
    """
    if not is_live():
        sid = "MOCK-CALL-" + secrets.token_hex(8).upper()
        return SendResult(sid=sid, is_mock=True, status="mocked")

    from twilio.rest import Client  # type: ignore[import-not-found]

    sid_env = _env("TWILIO_ACCOUNT_SID")
    auth_env = _env("TWILIO_AUTH_TOKEN")
    assert sid_env and auth_env, "twilio creds required when is_live()"

    client = Client(sid_env, auth_env)

    if twiml_url:
        # Bidirectional flow — Twilio GETs the TwiML, plays the prompt,
        # captures the spoken response, POSTs it back.
        url = twiml_url
        if ping_id and "ping_id=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}ping_id={ping_id}"
        call = client.calls.create(
            from_=voice_from(),
            to=to_number,
            url=url,
            method="POST",
        )
    else:
        # One-way alert mode
        import html as _html
        escaped = _html.escape(message)
        twiml = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response>'
            f'<Say voice="Polly.Aditi-Neural">{escaped}</Say>'
            f'<Pause length="1"/>'
            f'<Say voice="Polly.Aditi-Neural">{escaped}</Say>'
            f'</Response>'
        )
        call = client.calls.create(
            from_=voice_from(),
            to=to_number,
            twiml=twiml,
        )
    return SendResult(sid=call.sid, is_mock=False, status=call.status or "queued")
