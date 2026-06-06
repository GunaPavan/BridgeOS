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
        db.commit()
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

    db.commit()

    return InboundEmailProcessResult(
        persisted_email_id=persisted_email_id,
        matched_patient_id=patient.id,
        intent=getattr(classified.intent, "value", str(classified.intent)),
        confidence=classified.confidence,
        topic_published=topic_published,
        sns_message_id=sns_message_id,
    )
