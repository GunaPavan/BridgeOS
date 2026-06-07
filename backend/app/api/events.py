"""/system/events/* — topic catalogue + recent feed + dispatcher status."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.events import get_dispatcher
from app.events.dispatcher import list_subscribers
from app.events.topics import ALL_TOPICS
from app.integrations import sns_client
from app.schemas.event import (
    DispatcherStatus,
    EventOut,
    RepublishResult,
    TopicWithSubscribers,
)

router = APIRouter(prefix="/system/events", tags=["events"])


@router.get(
    "/topics",
    response_model=list[TopicWithSubscribers],
    summary="List configured topics + their in-process subscribers",
)
def list_topics() -> list[TopicWithSubscribers]:
    subs = list_subscribers()
    out = []
    for t in ALL_TOPICS:
        out.append(TopicWithSubscribers(topic=t.value, subscribers=subs.get(t.value, [])))
    return out


@router.get(
    "/recent",
    response_model=list[EventOut],
    summary="Last N published events across all topics",
)
def list_recent(
    topic: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> list[EventOut]:
    events = sns_client.recent_events(topic_name=topic, limit=limit)
    return [
        EventOut(
            message_id=e.message_id,
            topic_name=e.topic_name,
            body=e.body,
            published_at=datetime.fromtimestamp(e.published_at),
            is_mock=e.is_mock,
        )
        for e in events
    ]


@router.post(
    "/republish/{message_id}",
    response_model=RepublishResult,
    summary="Re-publish a stored event by MessageId (replay side effects)",
)
def republish_event(message_id: str) -> RepublishResult:
    result = sns_client.republish_event(message_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No event with id {message_id} in the recent history (max 500 per topic)",
        )
    return RepublishResult(
        original_message_id=message_id,
        new_message_id=result.message_id,
        topic_name=result.topic_name,
        is_mock=result.is_mock,
    )


@router.get(
    "/status",
    response_model=DispatcherStatus,
    summary="EventDispatcher worker stats",
)
def dispatcher_status() -> DispatcherStatus:
    subs = list_subscribers()
    topics_out = [
        TopicWithSubscribers(topic=t.value, subscribers=subs.get(t.value, []))
        for t in ALL_TOPICS
    ]
    d = get_dispatcher()
    if d is None:
        return DispatcherStatus(
            running=False,
            delivered=0,
            failed=0,
            last_tick_at=None,
            topics=topics_out,
        )
    return DispatcherStatus(
        running=True,
        delivered=d.stats.delivered,
        failed=d.stats.failed,
        last_tick_at=(
            datetime.fromtimestamp(d.stats.last_tick_at) if d.stats.last_tick_at else None
        ),
        topics=topics_out,
    )


# ---------------------------------------------------------------------------
# E16 — Lambda subscriber callback
# ---------------------------------------------------------------------------


@router.post(
    "/lambda-callback",
    summary="E16: Lambda subscriber callback — Lambda received an SNS event",
)
def lambda_callback(payload: dict) -> dict:
    """Lambda subscribers POST here to log that they received an SNS event.

    The in-process EventDispatcher is the actual side-effect runner; this
    endpoint just records that the Lambda subscriber also got the event,
    proving the cross-process redundancy works.
    """
    import logging as _log
    _log.getLogger(__name__).info(
        "Lambda subscriber callback: topic=%s, donor=%s, patient=%s, lambda_msg=%s",
        payload.get("topic"),
        payload.get("donor_id"),
        payload.get("patient_id"),
        payload.get("lambda_message_id"),
    )
    return {
        "received": True,
        "topic": payload.get("topic"),
        "lambda_message_id": payload.get("lambda_message_id"),
    }
