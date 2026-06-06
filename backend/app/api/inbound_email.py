"""/emails/inbound-webhook — accept simulated inbound emails for the demo
loop until SES receipt rules + a verified domain are wired in production.

Same processing pipeline runs whether the source is this webhook or the
real S3 poller — see app/services/inbound_email_handler.py.

POST /emails/inbound-webhook   (structured JSON, no SES infra needed)
POST /emails/inbound-raw       (raw RFC 822 MIME for testing the parser)
GET  /emails/inbound           (paginated inbound list, audit view)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db import get_db
from app.integrations.ses_inbound import ParsedInboundEmail, parse_raw_email
from app.models import EmailMessage
from app.services.inbound_email_handler import (
    InboundEmailProcessResult,
    process_inbound_email,
)

router = APIRouter(prefix="/emails", tags=["emails-inbound"])


# ---------- Request / response shapes ----------


class InboundWebhookRequest(BaseModel):
    """Structured payload that mimics what the SES → S3 poller produces."""

    from_email: EmailStr
    to_email: Optional[EmailStr] = None
    subject: str = ""
    body_text: str
    body_html: Optional[str] = None
    message_id: Optional[str] = None
    received_at: Optional[datetime] = None


class InboundProcessResultOut(BaseModel):
    persisted_email_id: Optional[uuid.UUID]
    matched_patient_id: Optional[uuid.UUID]
    intent: Optional[str]
    confidence: float
    topic_published: Optional[str]
    sns_message_id: Optional[str]
    reason: Optional[str] = None


class InboundEmailOut(BaseModel):
    id: uuid.UUID
    from_email: str
    to_email: str
    subject: str
    body: str
    caregiver_for_patient_id: Optional[uuid.UUID]
    ses_message_id: Optional[str]
    created_at: datetime
    status: str

    @classmethod
    def from_row(cls, em: EmailMessage) -> "InboundEmailOut":
        return cls(
            id=em.id,
            from_email=em.from_email or "",
            to_email=em.recipient_email or "",
            subject=em.subject or "",
            body=em.body or "",
            caregiver_for_patient_id=em.caregiver_for_patient_id,
            ses_message_id=em.ses_message_id,
            created_at=em.created_at,
            status=em.status,
        )


def _to_out(r: InboundEmailProcessResult) -> InboundProcessResultOut:
    return InboundProcessResultOut(
        persisted_email_id=r.persisted_email_id,
        matched_patient_id=r.matched_patient_id,
        intent=r.intent,
        confidence=r.confidence,
        topic_published=r.topic_published,
        sns_message_id=r.sns_message_id,
        reason=r.reason,
    )


# ---------- Endpoints ----------


@router.post(
    "/inbound-webhook",
    response_model=InboundProcessResultOut,
    summary=(
        "E7: ingest a structured inbound email payload (mimics SES → S3 poller "
        "output). Classifies + publishes to caregiver-reply-* SNS topic."
    ),
)
def inbound_webhook(
    payload: InboundWebhookRequest,
    db: Session = Depends(get_db),
) -> InboundProcessResultOut:
    parsed = ParsedInboundEmail(
        from_email=payload.from_email.lower(),
        to_email=(payload.to_email or "").lower(),
        subject=payload.subject,
        body_text=payload.body_text,
        body_html=payload.body_html,
        message_id=payload.message_id or f"sim-{uuid.uuid4().hex[:12]}",
        received_at=payload.received_at or datetime.utcnow(),
    )
    return _to_out(process_inbound_email(db, email_obj=parsed))


@router.post(
    "/inbound-raw",
    response_model=InboundProcessResultOut,
    summary="E7: ingest a raw RFC 822 MIME email body (exercises the parser)",
)
async def inbound_raw(
    request: Request, db: Session = Depends(get_db)
) -> InboundProcessResultOut:
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty request body")
    parsed = parse_raw_email(raw)
    if not parsed.from_email:
        raise HTTPException(status_code=400, detail="Missing From: header")
    return _to_out(process_inbound_email(db, email_obj=parsed))


@router.get(
    "/inbound",
    response_model=list[InboundEmailOut],
    summary="E7: list recent inbound emails (audit view)",
)
def list_inbound(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[InboundEmailOut]:
    rows = (
        db.query(EmailMessage)
        .filter(EmailMessage.direction == "inbound")
        .order_by(desc(EmailMessage.created_at))
        .limit(limit)
        .all()
    )
    return [InboundEmailOut.from_row(em) for em in rows]
