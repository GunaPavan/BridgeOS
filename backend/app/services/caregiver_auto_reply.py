"""E8.1 — auto-reply to caregiver emails based on classified intent.

When the inbound email handler classifies a caregiver email, this module
generates the right reply and sends it back via SES. Four reply paths:

  RESOLVED (STOP / DECLINE / ACCEPT) → "We've cancelled the outreach"
  URGENT  (MEDICAL_DEFER)             → "Coordinator notified, will call in 15 min"
  QUESTION (UNRELATED_QUESTION)       → Bedrock-generated contextual answer
                                        using the patient's actual data
  UNKNOWN                              → human-handoff template

All replies go via SES from ``ops@bridge-os.click`` (the verified domain).
Bedrock failures fall back to a generic template so the auto-reply never
fails silently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.integrations import ses_client
from app.models import EmailMessage, Patient, ReplyIntent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutoReplyResult:
    sent: bool
    message_id: str
    template_key: str
    body_excerpt: str
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def send_caregiver_auto_reply(
    db: Session,
    *,
    patient: Patient,
    intent: ReplyIntent,
    incoming_body: str,
    incoming_subject: str,
) -> AutoReplyResult:
    """Generate + send the right auto-reply for the caregiver's email."""
    caregiver_first = _first_name(patient.caregiver_name or patient.name)
    patient_first = _first_name(patient.name)

    if intent in (ReplyIntent.STOP, ReplyIntent.DECLINE, ReplyIntent.ACCEPT):
        subject, body, template_key = _render_resolved(
            caregiver_first, patient_first
        )
    elif intent == ReplyIntent.MEDICAL_DEFER:
        subject, body, template_key = _render_urgent(
            caregiver_first, patient_first
        )
    elif intent == ReplyIntent.UNRELATED_QUESTION:
        subject, body, template_key = _render_question_via_bedrock(
            caregiver_first, patient, incoming_body
        )
    else:
        subject, body, template_key = _render_human_handoff(
            caregiver_first, patient_first
        )

    # Add Gmail thread-friendly "Re:" prefix to the generic templates
    # (Re: your question / Re: your message). KEEP standalone subjects
    # like "URGENT — ..." and "Outreach cancelled" as-is so they stand out.
    if incoming_subject and subject.lower().startswith("re:"):
        subject = f"Re: {incoming_subject.removeprefix('Re: ').removeprefix('RE: ')}"

    result = ses_client.send_email(
        to=patient.caregiver_email or "",
        subject=subject,
        body=body,
    )

    # Persist the outbound EmailMessage so the audit trail is complete
    now = datetime.utcnow()
    db.add(
        EmailMessage(
            direction="outbound",
            recipient_email=patient.caregiver_email or "",
            from_email=ses_client.from_email(),
            subject=subject,
            body=body,
            template_key=template_key,
            language="en",
            ses_message_id=result.message_id,
            status=result.status,
            is_mock=result.is_mock,
            error_message=result.error_message,
            donor_id=None,
            caregiver_for_patient_id=patient.id,
            created_at=now,
            sent_at=now if result.status in ("sent", "mocked") else None,
        )
    )
    db.flush()

    return AutoReplyResult(
        sent=(result.status in ("sent", "mocked")),
        message_id=result.message_id,
        template_key=template_key,
        body_excerpt=body[:200],
        error_message=result.error_message,
    )


# ---------------------------------------------------------------------------
# Per-intent renderers
# ---------------------------------------------------------------------------


def _render_resolved(caregiver_first: str, patient_first: str) -> tuple[str, str, str]:
    body = (
        f"Hi {caregiver_first},\n\n"
        f"Got it — we've cancelled all pending donor outreach for {patient_first}. "
        f"No one else will be contacted for this slot.\n\n"
        f"If you change your mind or need help with the next cycle, just reply "
        f"to this email and the system will resume.\n\n"
        f"Take care,\nBridge OS coordinator\n"
    )
    return ("Outreach cancelled", body, "caregiver_auto_reply_resolved")


def _render_urgent(caregiver_first: str, patient_first: str) -> tuple[str, str, str]:
    body = (
        f"Hi {caregiver_first},\n\n"
        f"We've flagged your message about {patient_first} as URGENT. A coordinator "
        f"will call you on the registered phone number within the next 15 minutes.\n\n"
        f"If this is a medical emergency RIGHT NOW, please call your local hospital "
        f"or ambulance service immediately — Bridge OS is not a substitute for 108 / "
        f"emergency services.\n\n"
        f"Bridge OS coordinator\n"
    )
    return ("URGENT — coordinator will call you in 15 min", body, "caregiver_auto_reply_urgent")


def _render_question_via_bedrock(
    caregiver_first: str, patient: Patient, incoming_body: str
) -> tuple[str, str, str]:
    """Use the Care Agent (Bedrock) to generate a context-aware answer.

    Falls back to a templated 'we'll get back to you' if Bedrock isn't
    reachable (mock mode or live API failure).
    """
    template_key = "caregiver_auto_reply_question_bedrock"
    try:
        from app.agent import llm_client
        from datetime import date, timedelta as _td

        # Build a tight context block the model can ground on
        next_t = ""
        if patient.last_transfusion_date and patient.transfusion_cadence_days:
            next_d = patient.last_transfusion_date + _td(
                days=patient.transfusion_cadence_days
            )
            next_t = next_d.strftime("%a %d %b %Y")
        bridge_size = len(patient.bridge.memberships) if patient.bridge else 0

        context = (
            f"Patient: {patient.name}, age {patient.age}, blood {patient.blood_group}\n"
            f"Hospital: {patient.hospital}\n"
            f"Transfusion cadence: every {patient.transfusion_cadence_days} days\n"
            f"Next transfusion date: {next_t or 'not scheduled'}\n"
            f"Active donor count on bridge: {bridge_size}\n"
        )
        system_prompt = (
            "You are the Bridge OS Care Agent replying to a caregiver's email. "
            "Be warm, concise (3-5 sentences), and grounded ONLY in the patient context "
            "below. If the question is outside scope (medical advice, blood compatibility "
            "rules, drug interactions), say a human coordinator will follow up rather than "
            "guessing. Sign off as 'Bridge OS coordinator'. Do NOT include 'Subject:' or "
            "salutation — just the email body. Plain text only.\n\n"
            f"PATIENT CONTEXT:\n{context}"
        )
        response = llm_client.chat(
            system_prompt,
            [llm_client.ChatMessage(role="user", content=incoming_body)],
            max_tokens=400,
            temperature=0.4,
            task="chat",
        )
        body = (
            f"Hi {caregiver_first},\n\n"
            f"{response.text.strip()}\n"
        )
        return ("Re: your question", body, template_key)
    except Exception as exc:
        logger.exception("Bedrock auto-reply failed, using fallback")
        body = (
            f"Hi {caregiver_first},\n\n"
            f"Thanks for the message — a coordinator will reply to your question "
            f"within the next few hours. If it's urgent, you can also reach us "
            f"via WhatsApp.\n\n"
            f"Bridge OS coordinator\n"
        )
        return ("Re: your question", body, "caregiver_auto_reply_question_fallback")


def _render_human_handoff(caregiver_first: str, patient_first: str) -> tuple[str, str, str]:
    body = (
        f"Hi {caregiver_first},\n\n"
        f"Got your message about {patient_first}. A human coordinator will reply "
        f"within a few hours.\n\n"
        f"Bridge OS\n"
    )
    return ("Re: your message", body, "caregiver_auto_reply_handoff")


def _first_name(name: Optional[str]) -> str:
    if not name:
        return "there"
    return name.split()[0]
