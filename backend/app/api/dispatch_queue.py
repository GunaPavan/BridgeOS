"""/system/dispatch-queue/* — depth, peek, replay DLQ."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.integrations import sqs_client
from app.outreach.dispatch_queue import get_worker
from app.schemas.dispatch_queue import (
    DispatchMessageOut,
    DispatchQueueStatus,
    DeleteMessageResult,
    ReplayResult,
)

router = APIRouter(prefix="/system/dispatch-queue", tags=["dispatch-queue"])


@router.get(
    "/status",
    response_model=DispatchQueueStatus,
    summary="Queue depths + DispatchWorker stats",
)
def get_status() -> DispatchQueueStatus:
    depth = sqs_client.queue_depth()
    worker = get_worker()
    if worker is None:
        return DispatchQueueStatus(
            primary_depth=int(depth.get("primary", 0)),
            in_flight=int(depth.get("in_flight", 0)),
            dlq_depth=int(depth.get("dlq", 0)),
            mode=str(depth.get("mode", "mock")),
            error=depth.get("error"),
            worker_running=False,
            worker_received=0,
            worker_sent=0,
            worker_duplicates_skipped=0,
            worker_failed=0,
        )
    stats = worker.stats
    return DispatchQueueStatus(
        primary_depth=int(depth.get("primary", 0)),
        in_flight=int(depth.get("in_flight", 0)),
        dlq_depth=int(depth.get("dlq", 0)),
        mode=str(depth.get("mode", "mock")),
        error=depth.get("error"),
        worker_running=True,
        worker_received=stats.received,
        worker_sent=stats.sent,
        worker_duplicates_skipped=stats.duplicates_skipped,
        worker_failed=stats.failed,
        worker_last_drained_at=stats.last_drained_at,
        worker_started_at=stats.started_at,
    )


@router.get(
    "/messages",
    response_model=list[DispatchMessageOut],
    summary="Peek at primary queue messages (debug)",
)
def list_messages(limit: int = 10) -> list[DispatchMessageOut]:
    """READ ONLY peek — messages stay on the queue with their visibility
    timeout extended. Don't use this in production, it'll interfere with
    the worker."""
    msgs = sqs_client.receive_messages(max_messages=limit)
    return [
        DispatchMessageOut(
            message_id=m.message_id,
            body=m.body,
            is_mock=m.is_mock,
            queue_name=m.queue_name,
            approximate_receive_count=m.approximate_receive_count,
        )
        for m in msgs
    ]


@router.get(
    "/dlq",
    response_model=list[DispatchMessageOut],
    summary="Peek at DLQ messages",
)
def list_dlq(limit: int = 10) -> list[DispatchMessageOut]:
    msgs = sqs_client.list_dlq_messages(max_messages=limit)
    return [
        DispatchMessageOut(
            message_id=m.message_id,
            body=m.body,
            is_mock=m.is_mock,
            queue_name=m.queue_name,
            approximate_receive_count=m.approximate_receive_count,
        )
        for m in msgs
    ]


@router.post(
    "/replay-dlq",
    response_model=ReplayResult,
    summary="Re-enqueue everything in the DLQ onto the primary queue",
)
def replay_dlq() -> ReplayResult:
    result = sqs_client.replay_dlq()
    return ReplayResult(
        replayed=int(result.get("replayed", 0)),
        failed=int(result.get("failed", 0)),
    )


@router.delete(
    "/messages/{message_id}",
    response_model=DeleteMessageResult,
    summary="Drop a poison message by MessageId (checks primary + DLQ)",
)
def delete_message(message_id: str) -> DeleteMessageResult:
    removed = sqs_client.delete_message_by_id(message_id)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"No message with id {message_id} on primary or DLQ",
        )
    return DeleteMessageResult(message_id=message_id, removed=True)
