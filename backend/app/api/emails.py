"""/emails/* — list + filter the SES audit log, send a test email, view
distribution by template + status."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.integrations import ses_client
from app.models import EmailMessage
from app.schemas.email import (
    EmailDistribution,
    EmailMessageOut,
    EmailMessagesPage,
    EmailTemplateCount,
    TestEmailRequest,
    TestEmailResponse,
    VerifyIdentityRequest,
)

router = APIRouter(prefix="/emails", tags=["emails"])


@router.get("", response_model=EmailMessagesPage, summary="Paginated list with filters")
def list_emails(
    recipient: Optional[str] = Query(None),
    template_key: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    since_hours: Optional[int] = Query(None, ge=1, le=720),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> EmailMessagesPage:
    where = []
    if recipient:
        where.append(EmailMessage.recipient_email == recipient)
    if template_key:
        where.append(EmailMessage.template_key == template_key)
    if status:
        where.append(EmailMessage.status == status)
    if since_hours:
        cutoff = datetime.utcnow() - timedelta(hours=since_hours)
        where.append(EmailMessage.created_at >= cutoff)

    count_stmt = select(func.count(EmailMessage.id))
    list_stmt = select(EmailMessage).order_by(desc(EmailMessage.created_at))
    if where:
        count_stmt = count_stmt.where(and_(*where))
        list_stmt = list_stmt.where(and_(*where))

    total = int(db.execute(count_stmt).scalar_one() or 0)
    rows = db.execute(list_stmt.offset(offset).limit(limit)).scalars().all()
    return EmailMessagesPage(
        items=[EmailMessageOut.model_validate(r, from_attributes=True) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/distribution",
    response_model=EmailDistribution,
    summary="Aggregate email stats by template + status",
)
def get_distribution(
    window_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> EmailDistribution:
    cutoff = datetime.utcnow() - timedelta(days=window_days)
    rows = (
        db.execute(
            select(EmailMessage).where(EmailMessage.created_at >= cutoff)
        )
        .scalars()
        .all()
    )
    by_template: dict[str, EmailTemplateCount] = {}
    sent = failed = mocked = 0
    for r in rows:
        key = r.template_key or "(unknown)"
        m = by_template.setdefault(key, EmailTemplateCount(template_key=key))
        if r.status == "sent":
            m.sent += 1
            sent += 1
        elif r.status == "failed":
            m.failed += 1
            failed += 1
        elif r.status == "mocked":
            m.mocked += 1
            mocked += 1
        else:
            m.skipped += 1
    return EmailDistribution(
        window_days=window_days,
        total=len(rows),
        sent=sent,
        failed=failed,
        mocked=mocked,
        by_template=sorted(by_template.values(), key=lambda x: x.template_key),
    )


@router.get(
    "/{email_id}", response_model=EmailMessageOut, summary="Single email by id"
)
def get_email(
    email_id: uuid.UUID, db: Session = Depends(get_db)
) -> EmailMessageOut:
    row = db.get(EmailMessage, email_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return EmailMessageOut.model_validate(row, from_attributes=True)


@router.post(
    "/test",
    response_model=TestEmailResponse,
    summary="Send a test email through the live SES path (verify config)",
)
def send_test_email(
    body: TestEmailRequest, db: Session = Depends(get_db)
) -> TestEmailResponse:
    """Operator sanity-check: send a one-shot email through the same code
    path the digest job uses. Useful right after setting SES_FROM_EMAIL."""
    result = ses_client.send_email(
        to=body.recipient, subject=body.subject, body=body.body
    )
    now = datetime.utcnow()
    row = EmailMessage(
        direction="outbound",
        recipient_email=body.recipient,
        from_email=ses_client.from_email(),
        subject=body.subject,
        body=body.body,
        template_key="ops_test",
        language="en",
        ses_message_id=result.message_id,
        status=result.status,
        is_mock=result.is_mock,
        error_message=result.error_message,
        created_at=now,
        sent_at=now if result.status in ("sent", "mocked") else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return TestEmailResponse(
        message_id=result.message_id,
        is_mock=result.is_mock,
        status=result.status,
        persisted_id=row.id,
    )


@router.get("/system/identities", summary="List SES verified identities")
def list_identities() -> dict:
    return ses_client.list_verified_identities()


@router.post("/system/verify-identity", summary="Trigger SES verify-identity email")
def verify_identity(body: VerifyIdentityRequest) -> dict:
    return ses_client.verify_email_identity(body.email)
