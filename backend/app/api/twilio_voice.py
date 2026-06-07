"""Bidirectional voice flow via Twilio.

OUTBOUND voice call → /twilio/voice/twiml/ask?ping_id=...
                       → plays the question + <Gather speech>
                       → records donor's spoken answer

DONOR SPEAKS         → Twilio runs STT
                     → POSTs SpeechResult to /twilio/voice/twiml/answer?ping_id=...
                     → Bedrock classifier on the transcript
                     → mark ping accepted/declined/unsure
                     → reply with confirmation TwiML

DONOR HANGS UP / NO RESPONSE
                     → Twilio POSTs to /twilio/voice/status?ping_id=...
                     → mark ping NO_REPLY → next cycle escalates
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import OutreachPing, PingResponse, ReplyIntent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/twilio/voice", tags=["twilio-voice"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _twiml_response(body: str) -> PlainTextResponse:
    return PlainTextResponse(
        content=f'<?xml version="1.0" encoding="UTF-8"?>{body}',
        media_type="application/xml",
    )


def _public_base_url(request: Request) -> str:
    """Origin used to build TwiML action / status / redirect URLs.

    We prefer ``BRIDGE_OS_PUBLIC_URL`` because Starlette's ``request.base_url``
    returns ``http://...`` when the app sits behind a TLS-terminating ALB
    (the Fargate task receives plain HTTP). Twilio refuses to POST callbacks
    to ``http://`` action URLs, so falling back to ``request.base_url`` here
    causes a silent call drop right after the question plays.
    """
    import os
    explicit = os.environ.get("BRIDGE_OS_PUBLIC_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    return str(request.base_url).rstrip("/")


def _xml_escape(s: str) -> str:
    import html as _html
    return _html.escape(s)


def _voice_attr() -> str:
    """Indian-English Neural Polly voice. The Aditi voice has NO Neural
    variant — asking Twilio for ``Polly.Aditi-Neural`` triggers error 13520
    'Say: Invalid text' and the caller hears 'application error'. Kajal-Neural
    is the Neural-grade en-IN voice that ships with the standard Twilio
    catalog. Override per-deployment via TWILIO_VOICE_NAME (e.g.
    ``Polly.Aditi`` for standard fallback)."""
    import os
    name = os.environ.get("TWILIO_VOICE_NAME", "Polly.Kajal-Neural").strip()
    return f'voice="{name}"'


# ---------------------------------------------------------------------------
# Outbound: TwiML the call hits FIRST when it connects
# ---------------------------------------------------------------------------


@router.get("/twiml/ask")
@router.post("/twiml/ask")
async def voice_ask(request: Request, ping_id: Optional[str] = Query(None)):
    """First TwiML the call hits. Plays the question + opens a <Gather>
    so we can capture the donor's spoken response."""
    base_url = _public_base_url(request)
    action_url = f"{base_url}/twilio/voice/twiml/answer?ping_id={ping_id or ''}"
    status_url = f"{base_url}/twilio/voice/status?ping_id={ping_id or ''}"

    # Build the question from the ping/wave context
    question = _build_question_from_ping(ping_id)

    twiml = (
        f'<Response>'
        f'<Say {_voice_attr()}>{_xml_escape(question)}</Say>'
        f'<Gather input="speech" timeout="6" speechTimeout="auto" '
        f'action="{action_url}" method="POST" language="en-IN">'
        f'<Say {_voice_attr()}>Please say yes, no, or not sure.</Say>'
        f'</Gather>'
        # If user is silent past the gather timeout, fall through here
        f'<Say {_voice_attr()}>Sorry, we did not catch your response. '
        f'We will reach out again later. Goodbye.</Say>'
        f'<Redirect>{status_url}&amp;SpeechResult=NO_RESPONSE</Redirect>'
        f'</Response>'
    )
    return _twiml_response(twiml)


def _build_question_from_ping(ping_id: Optional[str]) -> str:
    """Build a contextual question using the actual patient + slot data.

    If the one-click demo (/admin/demo/fire-all) just composed a Bedrock
    voice question for this ping_id, return that — so the call hears the
    same LLM-written sentence the WhatsApp / SMS / email all carry. Falls
    back to a templated question if no cache hit, then to a generic one.
    """
    # Look up the Bedrock-composed question if /admin/demo/fire-all set it.
    if ping_id:
        try:
            from app.services.demo_outreach import get_cached_voice_question

            cached = get_cached_voice_question(ping_id)
            if cached:
                return cached
        except Exception:  # pragma: no cover — never let the cache break the call
            logger.exception("voice-question cache lookup failed for ping %s", ping_id)

    if not ping_id:
        return (
            "Hello, this is Bridge O S calling on behalf of Blood Warriors. "
            "We have an urgent blood requirement. Are you free to donate "
            "in the next two days?"
        )
    try:
        # Open a session just for the lookup
        from app.db import SessionLocal

        with SessionLocal() as db:
            from app.models import Patient

            ping = db.get(OutreachPing, uuid.UUID(ping_id))
            if ping is None or ping.wave is None or ping.wave.patient_id is None:
                return _build_question_from_ping(None)
            # OutreachWave has patient_id (FK) but no `patient` relationship —
            # accessing ping.wave.patient raises AttributeError. Fetch directly.
            patient = db.get(Patient, ping.wave.patient_id)
            if patient is None:
                return _build_question_from_ping(None)
            slot_str = ping.wave.slot_date.strftime("%a %d %B")
            hospital = patient.hospital
            blood = getattr(patient.blood_group, "value", str(patient.blood_group))
            return (
                f"Hello, this is Bridge O S calling on behalf of Blood Warriors. "
                f"We have an urgent requirement for blood type {blood} at {hospital} "
                f"on {slot_str}, for a child named {patient.name}. "
                f"Are you available to donate?"
            )
    except Exception:
        logger.exception("Failed to build voice question for ping %s", ping_id)
        return _build_question_from_ping(None)


# ---------------------------------------------------------------------------
# Inbound from Twilio: the spoken answer
# ---------------------------------------------------------------------------


@router.post("/twiml/answer")
async def voice_answer(
    ping_id: Optional[str] = Query(None),
    SpeechResult: str = Form(default=""),
    Confidence: str = Form(default="0"),
    CallSid: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Twilio POSTs here with SpeechResult after the donor speaks.

    We run the same Bedrock classifier we use for WhatsApp/email replies,
    map the intent to a PingResponse, and read a confirmation message back.
    """
    transcript = (SpeechResult or "").strip()
    try:
        confidence = float(Confidence)
    except ValueError:
        confidence = 0.0
    logger.info(
        "Voice answer: ping=%s, call=%s, transcript=%r, conf=%.2f",
        ping_id, CallSid, transcript, confidence,
    )

    if not transcript:
        confirmation = (
            "Sorry, we did not catch what you said. We will call back later. Goodbye."
        )
        _mark_no_reply(db, ping_id)
        return _twiml_response(
            f'<Response><Say {_voice_attr()}>{_xml_escape(confirmation)}</Say></Response>'
        )

    # Classify via Bedrock (or keyword fallback)
    from app.services.reply_classifier import classify_reply

    classified = classify_reply(transcript, language="en")
    intent = classified.intent

    # Map intent → action + confirmation script
    confirmation = _confirmation_for_intent(intent, transcript)
    _update_ping_from_voice(db, ping_id, intent)

    return _twiml_response(
        f'<Response>'
        f'<Say {_voice_attr()}>{_xml_escape(confirmation)}</Say>'
        f'<Pause length="1"/>'
        f'<Hangup/>'
        f'</Response>'
    )


@router.post("/status")
async def voice_status(
    ping_id: Optional[str] = Query(None),
    CallStatus: str = Form(default=""),
    SpeechResult: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Catch-all for call completion / no-answer events.

    Twilio also calls this URL when a Redirect is hit (e.g., user was silent
    past the Gather timeout). We mark NO_REPLY so the next escalation cycle
    picks the ping up.
    """
    logger.info(
        "Voice status: ping=%s, status=%s, speech=%r",
        ping_id, CallStatus, SpeechResult,
    )
    if SpeechResult == "NO_RESPONSE" or CallStatus in ("no-answer", "busy", "failed"):
        _mark_no_reply(db, ping_id)
    return PlainTextResponse("ok")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _confirmation_for_intent(intent: ReplyIntent, transcript: str) -> str:
    """Return the TTS line to read back to the donor."""
    if intent == ReplyIntent.ACCEPT:
        return (
            "Thank you so much. We have confirmed your slot. "
            "A coordinator will message you with the exact time and "
            "hospital details. Goodbye."
        )
    if intent == ReplyIntent.DECLINE:
        return (
            "No problem. Thanks for letting us know. "
            "We will reach out for future slots. Goodbye."
        )
    if intent == ReplyIntent.OUT_OF_TOWN:
        return (
            "Got it. We have you marked as out of town for the next week. "
            "Safe travels. Goodbye."
        )
    if intent == ReplyIntent.MEDICAL_DEFER:
        return (
            "Wishing you a quick recovery. We have paused requests for two weeks. "
            "Goodbye."
        )
    if intent == ReplyIntent.STOP:
        return (
            "You have been opted out. You will not receive further calls. "
            "Goodbye."
        )
    if intent == ReplyIntent.UNRELATED_QUESTION:
        return (
            "Got it. A human coordinator will call you back to answer "
            "your question. Goodbye."
        )
    # UNKNOWN / unclear
    return (
        "Sorry, we did not understand your response. "
        "A coordinator will call you back. Goodbye."
    )


def _update_ping_from_voice(
    db: Session, ping_id: Optional[str], intent: ReplyIntent
) -> None:
    if not ping_id:
        return
    try:
        ping = db.get(OutreachPing, uuid.UUID(ping_id))
    except Exception:
        return
    if ping is None:
        return
    now = datetime.utcnow()
    if intent == ReplyIntent.ACCEPT:
        ping.response = PingResponse.ACCEPTED
        ping.response_at = now
        # Also trigger the existing outreach acceptance flow
        try:
            from app.outreach.dispatch import confirm_outreach_acceptance
            confirm_outreach_acceptance(
                db, donor_id=ping.donor_id, slot_ref=f"v-{ping.id.hex[:6]}"
            )
        except Exception:
            logger.exception("confirm_outreach_acceptance failed for voice accept")
    elif intent == ReplyIntent.DECLINE:
        ping.response = PingResponse.DECLINED
        ping.response_at = now
    elif intent in (
        ReplyIntent.OUT_OF_TOWN, ReplyIntent.MEDICAL_DEFER, ReplyIntent.STOP,
        ReplyIntent.UNRELATED_QUESTION,
    ):
        # Leave as PENDING but mark as having responded; the cooldown / event
        # subscribers can fire via the standard SNS topics if needed.
        ping.response_at = now
    db.commit()


def _mark_no_reply(db: Session, ping_id: Optional[str]) -> None:
    if not ping_id:
        return
    try:
        ping = db.get(OutreachPing, uuid.UUID(ping_id))
    except Exception:
        return
    if ping is None:
        return
    if ping.response == PingResponse.PENDING:
        ping.response = PingResponse.NO_REPLY
        ping.response_at = datetime.utcnow()
        db.commit()
