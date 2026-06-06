"""``/reply-classifications/*`` — full CRUD + analytics over the reply
classifier audit log.

Used by:
  - Operator review: list + correct intents (feedback loop for re-training)
  - Reply intelligence panel on /analytics: distribution + confidence histo
  - Per-donor profile (/donors/[id]): per-donor reply history
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ReplyClassification, ReplyIntent
from app.schemas.reply import (
    ConfidenceBucket,
    FeedbackRequest,
    IntentCount,
    IntentDistribution,
    ReplyClassificationDetail,
    ReplyClassificationOut,
    ReplyClassificationsPage,
)

router = APIRouter(prefix="/reply-classifications", tags=["reply-classifier"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _alive() -> tuple:
    """Filter clause excluding soft-deleted rows."""
    return (ReplyClassification.deleted_at.is_(None),)


def _get_alive(db: Session, rc_id: uuid.UUID) -> ReplyClassification:
    rc = db.get(ReplyClassification, rc_id)
    if rc is None or rc.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ReplyClassification {rc_id} not found",
        )
    return rc


# ---------------------------------------------------------------------------
# List + single
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=ReplyClassificationsPage,
    summary="Paginated list with filters",
)
def list_classifications(
    donor_id: Optional[uuid.UUID] = Query(None),
    intent: Optional[ReplyIntent] = Query(None),
    confidence_gte: Optional[float] = Query(None, ge=0.0, le=1.0),
    from_date: Optional[datetime] = Query(None),
    include_deleted: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ReplyClassificationsPage:
    where = []
    if donor_id is not None:
        where.append(ReplyClassification.donor_id == donor_id)
    if intent is not None:
        where.append(ReplyClassification.intent == intent)
    if confidence_gte is not None:
        where.append(ReplyClassification.confidence >= confidence_gte)
    if from_date is not None:
        where.append(ReplyClassification.classified_at >= from_date)
    if not include_deleted:
        where.extend(_alive())

    count_stmt = select(func.count(ReplyClassification.id))
    list_stmt = select(ReplyClassification).order_by(
        desc(ReplyClassification.classified_at)
    )
    if where:
        count_stmt = count_stmt.where(and_(*where))
        list_stmt = list_stmt.where(and_(*where))

    total = int(db.execute(count_stmt).scalar_one() or 0)
    rows = db.execute(list_stmt.offset(offset).limit(limit)).scalars().all()
    return ReplyClassificationsPage(
        items=[ReplyClassificationOut.model_validate(r, from_attributes=True) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/distribution",
    response_model=IntentDistribution,
    summary="Aggregate intent counts + averages over a recent window",
)
def get_distribution(
    window_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> IntentDistribution:
    cutoff = datetime.utcnow() - timedelta(days=window_days)
    rows = (
        db.execute(
            select(ReplyClassification).where(
                and_(
                    ReplyClassification.classified_at >= cutoff,
                    *_alive(),
                )
            )
        )
        .scalars()
        .all()
    )
    counts = Counter(r.intent for r in rows)
    avg_conf = (
        sum(r.confidence for r in rows) / len(rows) if rows else 0.0
    )
    fallback_rate = (
        sum(1 for r in rows if r.used_fallback) / len(rows) if rows else 0.0
    )
    # Top 5 free-text reschedule reasons (deduplicated by frequency)
    reschedule_reasons = [
        r.extracted_reason for r in rows
        if r.intent == ReplyIntent.RESCHEDULE_REQUEST and r.extracted_reason
    ]
    reason_counter = Counter(reschedule_reasons)

    return IntentDistribution(
        window_days=window_days,
        total=len(rows),
        counts=[
            IntentCount(intent=i, count=counts.get(i, 0))
            for i in ReplyIntent
        ],
        avg_confidence=round(avg_conf, 4),
        fallback_rate=round(fallback_rate, 4),
        top_reschedule_reasons=[r for r, _ in reason_counter.most_common(5)],
    )


@router.get(
    "/by-donor/{donor_id}",
    response_model=ReplyClassificationsPage,
    summary="All classifications for one donor (newest first)",
)
def list_by_donor(
    donor_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ReplyClassificationsPage:
    rows = (
        db.execute(
            select(ReplyClassification)
            .where(and_(ReplyClassification.donor_id == donor_id, *_alive()))
            .order_by(desc(ReplyClassification.classified_at))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return ReplyClassificationsPage(
        items=[ReplyClassificationOut.model_validate(r, from_attributes=True) for r in rows],
        total=len(rows),
        limit=limit,
        offset=0,
    )


@router.get(
    "/confidence-histogram",
    response_model=list[ConfidenceBucket],
    summary="Confidence-bucketed counts (10 buckets) for the panel histogram",
)
def get_confidence_histogram(
    window_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> list[ConfidenceBucket]:
    cutoff = datetime.utcnow() - timedelta(days=window_days)
    rows = (
        db.execute(
            select(ReplyClassification.confidence).where(
                and_(
                    ReplyClassification.classified_at >= cutoff,
                    *_alive(),
                )
            )
        )
        .scalars()
        .all()
    )
    buckets = [ConfidenceBucket(low=i / 10, high=(i + 1) / 10, count=0) for i in range(10)]
    for c in rows:
        idx = min(9, max(0, int((c or 0.0) * 10)))
        buckets[idx].count += 1
    return buckets


@router.get(
    "/{rc_id}",
    response_model=ReplyClassificationDetail,
    summary="Single classification (includes raw model JSON)",
)
def get_classification(
    rc_id: uuid.UUID, db: Session = Depends(get_db)
) -> ReplyClassificationDetail:
    rc = _get_alive(db, rc_id)
    return ReplyClassificationDetail.model_validate(rc, from_attributes=True)


# ---------------------------------------------------------------------------
# Feedback + soft delete
# ---------------------------------------------------------------------------


@router.post(
    "/{rc_id}/feedback",
    response_model=ReplyClassificationDetail,
    summary="Operator corrects the picked intent (training-set feedback)",
)
def submit_feedback(
    rc_id: uuid.UUID,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
) -> ReplyClassificationDetail:
    rc = _get_alive(db, rc_id)
    rc.operator_corrected_intent = body.corrected_intent
    rc.operator_feedback_note = body.note
    rc.feedback_at = datetime.utcnow()
    db.commit()
    db.refresh(rc)
    return ReplyClassificationDetail.model_validate(rc, from_attributes=True)


@router.delete(
    "/{rc_id}",
    summary="Soft-delete a classification row (operator override / privacy)",
)
def soft_delete(
    rc_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:
    rc = _get_alive(db, rc_id)
    rc.deleted_at = datetime.utcnow()
    db.commit()
    return {"id": str(rc.id), "deleted_at": rc.deleted_at.isoformat() + "Z"}
