"""AWS SQS client with in-memory mock fallback.

Mirror of ``app.integrations.ses_client`` — same dataclass shape, same mock-
mode behaviour. Used by the dispatch queue (`app.outreach.dispatch_queue`)
which buffers every Twilio/SES outbound between the allocator and the
external API.

QUEUE NAMING
------------
We auto-provision two queues on first use:
    {prefix}-dispatch       — primary
    {prefix}-dispatch-dlq   — dead-letter (3 strikes → here)

``prefix`` comes from ``app.integrations.aws.resource_prefix()``. Both queues
get the standard ``Project=bridge-os`` tag set so cleanup is one tag-filtered
delete.

MOCK MODE
---------
When AWS isn't reachable, ``publish/poll/delete`` operate against a process-
local in-memory queue. This lets the dispatch worker thread keep ticking in
dev / tests without ever hitting AWS.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from app.integrations.aws import (
    aws_available,
    get_boto3_client,
    get_region,
    resource_prefix,
    resource_tags,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PublishResult:
    message_id: str
    is_mock: bool
    queue_name: str


@dataclass(frozen=True)
class SQSMessage:
    """One message pulled off the queue.

    ``receipt_handle`` is opaque — pass it back to ``delete_message`` to
    remove the message once you've processed it. ``approximate_receive_count``
    helps the worker decide whether to give up and let SQS send to DLQ.
    """

    message_id: str
    body: dict
    receipt_handle: str
    queue_name: str
    is_mock: bool
    approximate_receive_count: int = 1


# ---------------------------------------------------------------------------
# Mock backend (in-memory deque per queue name)
# ---------------------------------------------------------------------------


@dataclass
class _MockQueue:
    messages: deque = field(default_factory=deque)
    receive_counts: dict[str, int] = field(default_factory=dict)
    visibility_until: dict[str, float] = field(default_factory=dict)
    in_flight: dict[str, dict] = field(default_factory=dict)  # mid -> raw payload
    dlq: deque = field(default_factory=deque)
    lock: threading.Lock = field(default_factory=threading.Lock)


_MOCK_QUEUES: dict[str, _MockQueue] = {}
_MOCK_LOCK = threading.Lock()
_MOCK_MAX_RECEIVES = 3  # matches the live DLQ policy below
_MOCK_VISIBILITY_TIMEOUT_SECONDS = 30


def _get_mock_queue(name: str) -> _MockQueue:
    with _MOCK_LOCK:
        return _MOCK_QUEUES.setdefault(name, _MockQueue())


def _reset_mock_queues_for_tests() -> None:
    """Test helper — never called in production."""
    with _MOCK_LOCK:
        _MOCK_QUEUES.clear()


# ---------------------------------------------------------------------------
# Queue name resolution
# ---------------------------------------------------------------------------


def dispatch_queue_name() -> str:
    """Primary outbound dispatch queue."""
    return f"{resource_prefix()}-dispatch"


def dispatch_dlq_name() -> str:
    """Dead-letter queue for 3-strike messages."""
    return f"{resource_prefix()}-dispatch-dlq"


# ---------------------------------------------------------------------------
# Queue URL cache (live mode only)
# ---------------------------------------------------------------------------


_QUEUE_URL_CACHE: dict[str, str] = {}
_QUEUE_URL_LOCK = threading.Lock()


def _ensure_queue_exists(queue_name: str, *, is_dlq: bool = False) -> str:
    """Create the queue if missing, return its URL.

    Live mode only. Caches the URL so we only hit ListQueues / CreateQueue
    on first use.
    """
    with _QUEUE_URL_LOCK:
        if queue_name in _QUEUE_URL_CACHE:
            return _QUEUE_URL_CACHE[queue_name]

    client = get_boto3_client("sqs", region=get_region())

    # Try to look up the URL first
    try:
        url = client.get_queue_url(QueueName=queue_name)["QueueUrl"]
    except client.exceptions.QueueDoesNotExist:  # type: ignore[union-attr]
        attrs = {
            "MessageRetentionPeriod": "1209600",  # 14 days
            "VisibilityTimeout": str(_MOCK_VISIBILITY_TIMEOUT_SECONDS),
        }
        url = client.create_queue(QueueName=queue_name, Attributes=attrs)["QueueUrl"]
        try:
            arn = client.get_queue_attributes(
                QueueUrl=url, AttributeNames=["QueueArn"]
            )["Attributes"]["QueueArn"]
            tags = {t["Key"]: t["Value"] for t in resource_tags()}
            tags["Type"] = "dlq" if is_dlq else "primary"
            client.tag_queue(QueueUrl=url, Tags=tags)
        except Exception:  # pragma: no cover
            logger.exception("Failed to tag SQS queue %s", queue_name)

    with _QUEUE_URL_LOCK:
        _QUEUE_URL_CACHE[queue_name] = url
    return url


def _ensure_dlq_redrive(primary_url: str, dlq_url: str) -> None:
    """Wire the primary queue's RedrivePolicy at the DLQ."""
    try:
        client = get_boto3_client("sqs", region=get_region())
        dlq_arn = client.get_queue_attributes(
            QueueUrl=dlq_url, AttributeNames=["QueueArn"]
        )["Attributes"]["QueueArn"]
        client.set_queue_attributes(
            QueueUrl=primary_url,
            Attributes={
                "RedrivePolicy": json.dumps(
                    {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": _MOCK_MAX_RECEIVES}
                ),
            },
        )
    except Exception:  # pragma: no cover
        logger.exception("Failed to set RedrivePolicy on %s", primary_url)


# ---------------------------------------------------------------------------
# Public API: publish / receive / delete
# ---------------------------------------------------------------------------


def publish(
    body: dict,
    *,
    queue_name: Optional[str] = None,
) -> PublishResult:
    """Publish a JSON message onto the dispatch queue (or a named queue)."""
    name = queue_name or dispatch_queue_name()
    payload = json.dumps(body, default=str)

    if not aws_available():
        mq = _get_mock_queue(name)
        mid = "MOCK-SQS-" + secrets.token_hex(8).upper()
        with mq.lock:
            mq.messages.append(
                {
                    "MessageId": mid,
                    "Body": payload,
                    "ReceiptHandle": "rh-" + secrets.token_hex(8),
                }
            )
        return PublishResult(message_id=mid, is_mock=True, queue_name=name)

    try:
        client = get_boto3_client("sqs", region=get_region())
        url = _ensure_queue_exists(name)
        resp = client.send_message(QueueUrl=url, MessageBody=payload)
        return PublishResult(
            message_id=resp.get("MessageId", "UNKNOWN"),
            is_mock=False,
            queue_name=name,
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("SQS publish failed to %s", name)
        # Fall back to mock so the loop doesn't die
        mq = _get_mock_queue(name)
        mid = "FAIL-FALLBACK-" + secrets.token_hex(8).upper()
        with mq.lock:
            mq.messages.append(
                {"MessageId": mid, "Body": payload, "ReceiptHandle": "rh-fail"}
            )
        return PublishResult(message_id=mid, is_mock=True, queue_name=name)


def receive_messages(
    *,
    queue_name: Optional[str] = None,
    max_messages: int = 10,
    wait_seconds: int = 0,
) -> list[SQSMessage]:
    """Pull up to ``max_messages`` from the queue.

    In live mode this uses long-polling (``wait_seconds`` up to 20). In mock
    mode, ``wait_seconds`` is ignored and we return immediately.
    """
    name = queue_name or dispatch_queue_name()

    if not aws_available():
        mq = _get_mock_queue(name)
        out: list[SQSMessage] = []
        now = time.time()
        with mq.lock:
            # First, sweep in-flight messages whose visibility has expired
            # back into the visible queue (or into the DLQ on max-receives).
            expired_back = []
            for mid in list(mq.in_flight.keys()):
                if mq.visibility_until.get(mid, 0) <= now:
                    raw = mq.in_flight.pop(mid)
                    count = mq.receive_counts.get(mid, 0)
                    if count >= _MOCK_MAX_RECEIVES:
                        mq.dlq.append(raw)
                        mq.visibility_until.pop(mid, None)
                    else:
                        expired_back.append(raw)
            # FIFO-ish: appended in iteration order
            for raw in expired_back:
                mq.messages.append(raw)

            while mq.messages and len(out) < max_messages:
                raw = mq.messages.popleft()
                mid = raw["MessageId"]
                count = mq.receive_counts.get(mid, 0) + 1
                mq.receive_counts[mid] = count
                mq.visibility_until[mid] = now + _MOCK_VISIBILITY_TIMEOUT_SECONDS
                # Move into in-flight so it's not visible until visibility expires
                # OR delete_message is called (which removes from in_flight).
                mq.in_flight[mid] = raw
                try:
                    body_dict = json.loads(raw["Body"])
                except Exception:
                    body_dict = {"_raw": raw["Body"]}
                out.append(
                    SQSMessage(
                        message_id=mid,
                        body=body_dict,
                        receipt_handle=raw["ReceiptHandle"],
                        queue_name=name,
                        is_mock=True,
                        approximate_receive_count=count,
                    )
                )
        return out

    client = get_boto3_client("sqs", region=get_region())
    url = _ensure_queue_exists(name)
    try:
        resp = client.receive_message(
            QueueUrl=url,
            MaxNumberOfMessages=min(10, max_messages),
            WaitTimeSeconds=min(20, wait_seconds),
            AttributeNames=["ApproximateReceiveCount"],
        )
    except Exception:  # pragma: no cover
        logger.exception("SQS receive failed from %s", name)
        return []

    out = []
    for m in resp.get("Messages", []):
        try:
            body_dict = json.loads(m.get("Body", "{}"))
        except Exception:
            body_dict = {"_raw": m.get("Body", "")}
        out.append(
            SQSMessage(
                message_id=m.get("MessageId", "UNKNOWN"),
                body=body_dict,
                receipt_handle=m["ReceiptHandle"],
                queue_name=name,
                is_mock=False,
                approximate_receive_count=int(
                    m.get("Attributes", {}).get("ApproximateReceiveCount", 1)
                ),
            )
        )
    return out


def delete_message(
    *, receipt_handle: str, queue_name: Optional[str] = None
) -> bool:
    name = queue_name or dispatch_queue_name()
    if not aws_available():
        mq = _get_mock_queue(name)
        with mq.lock:
            # Delete from in-flight first — that's where a just-received
            # message lives. Fall back to scanning visible queue for safety.
            target = None
            for mid, raw in list(mq.in_flight.items()):
                if raw["ReceiptHandle"] == receipt_handle:
                    target = mq.in_flight.pop(mid)
                    mq.receive_counts.pop(mid, None)
                    mq.visibility_until.pop(mid, None)
                    break
            if target is None:
                keep = []
                while mq.messages:
                    m = mq.messages.popleft()
                    if m["ReceiptHandle"] == receipt_handle and target is None:
                        target = m
                        continue
                    keep.append(m)
                mq.messages.extend(keep)
                if target is not None:
                    mq.receive_counts.pop(target["MessageId"], None)
                    mq.visibility_until.pop(target["MessageId"], None)
        return True

    try:
        client = get_boto3_client("sqs", region=get_region())
        url = _ensure_queue_exists(name)
        client.delete_message(QueueUrl=url, ReceiptHandle=receipt_handle)
        return True
    except Exception:  # pragma: no cover
        logger.exception("SQS delete_message failed for %s", name)
        return False


def delete_message_by_id(message_id: str, *, queue_name: Optional[str] = None) -> bool:
    """Drop a specific message from the queue by MessageId.

    Used by the poison-pill DELETE endpoint. In mock mode we walk the
    visible queue + in-flight set; in live mode we have to receive the
    message (with a high visibility timeout) and delete by receipt
    handle, since SQS has no native delete-by-id.

    Returns ``True`` if a message was actually removed.
    """
    name = queue_name or dispatch_queue_name()

    if not aws_available():
        # Check both the explicitly named queue AND its sibling DLQ — callers
        # often don't know which queue holds the poison.
        candidate_names = [name]
        if name == dispatch_queue_name():
            candidate_names.append(dispatch_dlq_name())
        elif name == dispatch_dlq_name():
            candidate_names.append(dispatch_queue_name())
        for qname in candidate_names:
            mq = _get_mock_queue(qname)
            with mq.lock:
                # In-flight first
                if message_id in mq.in_flight:
                    mq.in_flight.pop(message_id, None)
                    mq.receive_counts.pop(message_id, None)
                    mq.visibility_until.pop(message_id, None)
                    return True
                keep = []
                removed = False
                while mq.messages:
                    m = mq.messages.popleft()
                    if not removed and m["MessageId"] == message_id:
                        removed = True
                        continue
                    keep.append(m)
                mq.messages.extend(keep)
                if removed:
                    mq.receive_counts.pop(message_id, None)
                    mq.visibility_until.pop(message_id, None)
                    return True
                # Also walk the secondary `dlq` deque on the primary queue
                # (legacy spillover from receive_messages when receive_count
                # exceeds _MOCK_MAX_RECEIVES).
                spillover_keep = []
                spillover_removed = False
                while mq.dlq:
                    m = mq.dlq.popleft()
                    if not spillover_removed and m["MessageId"] == message_id:
                        spillover_removed = True
                        continue
                    spillover_keep.append(m)
                mq.dlq.extend(spillover_keep)
                if spillover_removed:
                    return True
        return False

    # Live mode: receive a batch with a long visibility timeout, find the
    # one we want, delete it, return the rest via 0-second timeout.
    try:
        client = get_boto3_client("sqs", region=get_region())
        url = _ensure_queue_exists(name)
        # Try DLQ too — caller may not know which queue holds the poison
        for try_url in (url, _ensure_queue_exists(dispatch_dlq_name(), is_dlq=True)):
            try:
                resp = client.receive_message(
                    QueueUrl=try_url,
                    MaxNumberOfMessages=10,
                    VisibilityTimeout=120,
                    WaitTimeSeconds=0,
                )
                hits = [m for m in resp.get("Messages", []) if m.get("MessageId") == message_id]
                others = [m for m in resp.get("Messages", []) if m.get("MessageId") != message_id]
                if hits:
                    client.delete_message(QueueUrl=try_url, ReceiptHandle=hits[0]["ReceiptHandle"])
                    # Release the visibility hold on the others
                    for o in others:
                        try:
                            client.change_message_visibility(
                                QueueUrl=try_url,
                                ReceiptHandle=o["ReceiptHandle"],
                                VisibilityTimeout=0,
                            )
                        except Exception:  # pragma: no cover
                            logger.warning("Failed to release visibility on %s", o.get("MessageId"))
                    return True
                # Release the holds we acquired on this queue before trying the next
                for m in resp.get("Messages", []):
                    try:
                        client.change_message_visibility(
                            QueueUrl=try_url,
                            ReceiptHandle=m["ReceiptHandle"],
                            VisibilityTimeout=0,
                        )
                    except Exception:  # pragma: no cover
                        logger.warning("Failed to release visibility on %s", m.get("MessageId"))
            except Exception:  # pragma: no cover
                logger.exception("delete_message_by_id receive failed on %s", try_url)
        return False
    except Exception:  # pragma: no cover
        logger.exception("delete_message_by_id failed for %s", message_id)
        return False


def queue_depth(queue_name: Optional[str] = None) -> dict:
    """Return primary + DLQ depths for the dispatch queue."""
    primary = queue_name or dispatch_queue_name()
    dlq = dispatch_dlq_name()
    if not aws_available():
        pmq = _get_mock_queue(primary)
        dmq = _get_mock_queue(dlq)
        with pmq.lock:
            primary_depth = len(pmq.messages)
        with dmq.lock:
            dlq_depth = len(pmq.dlq) + len(dmq.messages)
        return {
            "primary": primary_depth,
            "dlq": dlq_depth,
            "in_flight": 0,
            "mode": "mock",
        }

    try:
        client = get_boto3_client("sqs", region=get_region())
        url = _ensure_queue_exists(primary)
        attrs = client.get_queue_attributes(
            QueueUrl=url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
            ],
        )["Attributes"]
        dlq_url = _ensure_queue_exists(dlq, is_dlq=True)
        dlq_attrs = client.get_queue_attributes(
            QueueUrl=dlq_url, AttributeNames=["ApproximateNumberOfMessages"]
        )["Attributes"]
        return {
            "primary": int(attrs.get("ApproximateNumberOfMessages", 0)),
            "in_flight": int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0)),
            "dlq": int(dlq_attrs.get("ApproximateNumberOfMessages", 0)),
            "mode": "live",
        }
    except Exception as exc:  # pragma: no cover
        logger.exception("SQS queue_depth failed")
        return {"primary": 0, "in_flight": 0, "dlq": 0, "mode": "live", "error": str(exc)[:200]}


def list_dlq_messages(*, max_messages: int = 10) -> list[SQSMessage]:
    """Peek at DLQ messages without deleting them (debug + replay UI)."""
    return receive_messages(queue_name=dispatch_dlq_name(), max_messages=max_messages)


def replay_dlq(*, max_messages: int = 50) -> dict:
    """Move every DLQ message back onto the primary queue."""
    dlq = dispatch_dlq_name()
    primary = dispatch_queue_name()
    replayed = 0
    failed = 0
    while True:
        msgs = receive_messages(queue_name=dlq, max_messages=max_messages)
        if not msgs:
            break
        for m in msgs:
            try:
                publish(m.body, queue_name=primary)
                delete_message(receipt_handle=m.receipt_handle, queue_name=dlq)
                replayed += 1
            except Exception:  # pragma: no cover
                failed += 1
        if len(msgs) < max_messages:
            break
    return {"replayed": replayed, "failed": failed}
