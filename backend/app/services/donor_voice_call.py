"""E11.1 — bidirectional voice call to a donor.

Used when a donor hasn't responded to WhatsApp / SMS within their tier
threshold AND we want to TRY a phone call before giving up.

Different from coordinator escalation (one-way TTS alert):
  - Bidirectional: donor answers, says yes/no/maybe, we classify with Bedrock
  - Hits ``/twilio/voice/twiml/ask?ping_id=X`` which serves dynamic TwiML
    grounded on the patient's actual context (name, hospital, slot date)
  - Twilio captures speech via STT, POSTs to /twilio/voice/twiml/answer
  - Bedrock classifies the spoken response → updates OutreachPing accordingly

Requires ``BRIDGE_OS_PUBLIC_URL`` env var set to the public base URL of the
backend (e.g. https://api.bridge-os.click). Without it, the function
returns a "skipped" result and leaves the ping for the next escalation cycle.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.integrations import twilio_client
from app.models import Donor, OutreachPing

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DonorCallResult:
    placed: bool
    call_sid: str
    is_mock: bool
    skipped_reason: Optional[str] = None


def place_donor_voice_call(db: Session, *, ping: OutreachPing) -> DonorCallResult:
    """Place a bidirectional voice call to the donor for this ping.

    The TwiML the call hits ON THE WIRE is built dynamically by
    /twilio/voice/twiml/ask — see app/api/twilio_voice.py.
    """
    base_url = os.environ.get("BRIDGE_OS_PUBLIC_URL")
    if not base_url:
        return DonorCallResult(
            placed=False, call_sid="", is_mock=True,
            skipped_reason="BRIDGE_OS_PUBLIC_URL not set",
        )

    donor = db.get(Donor, ping.donor_id)
    if donor is None or not donor.phone:
        return DonorCallResult(
            placed=False, call_sid="", is_mock=True,
            skipped_reason="donor missing or no phone",
        )

    # Twilio fetches this URL when the call connects; the endpoint builds
    # the TwiML using the ping's wave + patient data.
    twiml_url = f"{base_url.rstrip('/')}/twilio/voice/twiml/ask"

    result = twilio_client.place_voice_call(
        to_number=donor.phone,
        message="",  # ignored when twiml_url is set
        twiml_url=twiml_url,
        ping_id=str(ping.id),
    )
    logger.info(
        "Placed donor voice call: ping=%s, donor=%s, sid=%s, mock=%s",
        ping.id, donor.phone, result.sid, result.is_mock,
    )
    return DonorCallResult(
        placed=True, call_sid=result.sid, is_mock=result.is_mock
    )
