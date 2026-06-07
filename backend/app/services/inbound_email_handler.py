"""Process one parsed inbound email through the automation loop.

INPUT:  ParsedInboundEmail (from SES S3 or from /emails/inbound-webhook)
        Includes from_email, subject, body_text.

PIPELINE (mirror of /whatsapp/webhook):
    1. Look up Patient by caregiver_email
    2. Persist EmailMessage row (direction=inbound)
    3. Run Bedrock reply classifier on body_text
    4. Map intent to caregiver-event topic:
        STOP / DECLINE / OPT_OUT  → CAREGIVER_REPLY_RESOLVED
        URGENT / MEDICAL_DEFER    → CAREGIVER_REPLY_URGENT
        UNRELATED_QUESTION        → CAREGIVER_REPLY_QUESTION
        ACCEPT                    → CAREGIVER_REPLY_RESOLVED (legacy "we sorted it")
        anything else             → no publish (audit row stays)
    5. Side effect runs via in-process subscriber (cancel pending outreach
       for the patient, etc.) — same EventDispatcher loop that handles
       donor WhatsApp replies.

OUTPUT: InboundEmailProcessResult — what happened, what was published.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.events import (
    publish_caregiver_reply_question,
    publish_caregiver_reply_resolved,
    publish_caregiver_reply_urgent,
)
from app.integrations.ses_inbound import ParsedInboundEmail
from app.models import EmailMessage, Patient, ReplyIntent
from app.services.reply_classifier import classify_reply

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InboundEmailProcessResult:
    persisted_email_id: Optional[uuid.UUID]
    matched_patient_id: Optional[uuid.UUID]
    intent: Optional[str]
    confidence: float
    topic_published: Optional[str]
    sns_message_id: Optional[str]
    reason: Optional[str] = None  # set when nothing happened


def process_inbound_email(
    db: Session, *, email_obj: ParsedInboundEmail
) -> InboundEmailProcessResult:
    """End-to-end ingestion of one parsed inbound email.

    Idempotent on (from_email, message_id) — re-processing the same SES
    message id is a no-op.
    """
    # Idempotency: if this message_id was already processed, skip
    if email_obj.message_id:
        existing = (
            db.query(EmailMessage)
            .filter(
                EmailMessage.direction == "inbound",
                EmailMessage.ses_message_id == email_obj.message_id,
            )
            .first()
        )
        if existing is not None:
            return InboundEmailProcessResult(
                persisted_email_id=existing.id,
                matched_patient_id=existing.caregiver_for_patient_id,
                intent=None,
                confidence=0.0,
                topic_published=None,
                sns_message_id=None,
                reason="duplicate_message_id",
            )

    # 1. Match caregiver
    sender = (email_obj.from_email or "").lower()
    patient = (
        db.query(Patient).filter(Patient.caregiver_email == sender).first()
        if sender
        else None
    )

    # 2. Persist EmailMessage row (always, even on no match)
    row = EmailMessage(
        direction="inbound",
        recipient_email=email_obj.to_email or "",
        from_email=sender,
        subject=email_obj.subject or "",
        body=email_obj.body_text or "",
        template_key=None,
        language="en",
        ses_message_id=email_obj.message_id or None,
        status="received",
        is_mock=False,  # by the time we get here it's a real email
        error_message=None,
        donor_id=None,
        caregiver_for_patient_id=patient.id if patient else None,
        created_at=email_obj.received_at,
        sent_at=None,
    )
    db.add(row)
    db.flush()
    persisted_email_id = row.id

    if patient is None:
        # Used to silently return here, which meant every demo-button email
        # reply landed in a black hole (the demo doesn't set the donor's
        # gmail as a patient.caregiver_email, so the lookup always fails).
        # Now: still send an LLM-composed acknowledgement back so the loop
        # closes visibly for the operator. Bedrock classifies the reply
        # into ACCEPT/DECLINE/MAYBE/STOP/UNCLEAR and writes a 2-line ack.
        db.commit()
        try:
            from datetime import datetime as _dt

            from app.integrations import ses_client
            from app.services.demo_outreach import compose_inbound_reply
            from app.services.reply_classifier import classify_reply as _classify

            classified = _classify(email_obj.body_text or "", language="en")
            intent_name = getattr(classified.intent, "name", str(classified.intent))
            composed = compose_inbound_reply(
                donor_name="",
                patient_name="",
                intent=intent_name,
                inbound_body=email_obj.body_text or "",
                language="en",
            )
            reply_subject = (
                f"Re: {email_obj.subject}"
                if email_obj.subject and not email_obj.subject.lower().startswith("re:")
                else (email_obj.subject or "Re: your message")
            )
            send_result = ses_client.send_email(
                to=email_obj.from_email,
                subject=reply_subject,
                body=composed.text,
            )
            # Persist the outbound auto-reply so /emails surfaces it too.
            db.add(
                EmailMessage(
                    direction="outbound",
                    recipient_email=email_obj.from_email,
                    from_email=ses_client.from_email(),
                    subject=reply_subject,
                    body=composed.text,
                    template_key=f"unknown_sender_ack_{composed.source}",
                    language="en",
                    ses_message_id=send_result.message_id,
                    status=send_result.status,
                    is_mock=send_result.is_mock,
                    error_message=send_result.error_message,
                    created_at=_dt.utcnow(),
                    sent_at=_dt.utcnow() if send_result.status in ("sent", "mocked") else None,
                )
            )
            db.commit()
            logger.info(
                "unknown-sender auto-reply sent to %s via %s (sid=%s, intent=%s, model=%s)",
                email_obj.from_email, composed.source, send_result.message_id,
                intent_name, composed.model,
            )
        except Exception:
            logger.exception("unknown-sender auto-reply failed for %s", email_obj.from_email)
        return InboundEmailProcessResult(
            persisted_email_id=persisted_email_id,
            matched_patient_id=None,
            intent=None,
            confidence=0.0,
            topic_published=None,
            sns_message_id=None,
            reason="unknown_sender",
        )

    # 3. Classify the body. We do NOT write a ReplyClassification audit row
    # here because that table's schema is donor-centric (donor_id NOT NULL).
    # For caregiver emails the EmailMessage row above already captures the
    # body; the SNS publish records the classified intent.
    classified = classify_reply(email_obj.body_text, language="en")

    # 4. Map intent → caregiver topic
    topic_published: Optional[str] = None
    sns_message_id: Optional[str] = None

    excerpt = (email_obj.body_text or "")[:300]
    if classified.intent in (ReplyIntent.STOP, ReplyIntent.DECLINE, ReplyIntent.ACCEPT):
        sns_message_id = publish_caregiver_reply_resolved(
            patient_id=patient.id,
            email_message_id=persisted_email_id,
            body_excerpt=excerpt,
        )
        topic_published = "caregiver-reply-resolved"
    elif classified.intent == ReplyIntent.MEDICAL_DEFER:
        sns_message_id = publish_caregiver_reply_urgent(
            patient_id=patient.id,
            email_message_id=persisted_email_id,
            body_excerpt=excerpt,
        )
        topic_published = "caregiver-reply-urgent"
    elif classified.intent == ReplyIntent.UNRELATED_QUESTION:
        sns_message_id = publish_caregiver_reply_question(
            patient_id=patient.id,
            email_message_id=persisted_email_id,
            body_excerpt=excerpt,
        )
        topic_published = "caregiver-reply-question"

    # E8.1: send an automated reply email back. Different paths per intent:
    #   RESOLVED/STOP → "we've cancelled, no one else will be contacted"
    #   URGENT        → "coordinator will call you in 15 min"
    #   QUESTION      → Bedrock-generated contextual answer using patient data
    #   UNKNOWN/other → human-handoff template
    try:
        from app.services.caregiver_auto_reply import send_caregiver_auto_reply

        send_caregiver_auto_reply(
            db,
            patient=patient,
            intent=classified.intent,
            incoming_body=email_obj.body_text or "",
            incoming_subject=email_obj.subject or "",
        )
    except Exception:
        # Never break the loop because the auto-reply failed
        logger.exception("Auto-reply send failed for patient %s", patient.id)

    db.commit()

    return InboundEmailProcessResult(
        persisted_email_id=persisted_email_id,
        matched_patient_id=patient.id,
        intent=getattr(classified.intent, "value", str(classified.intent)),
        confidence=classified.confidence,
        topic_published=topic_published,
        sns_message_id=sns_message_id,
    )
