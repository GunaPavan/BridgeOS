"""AWS SNS client with in-memory mock fallback.

We use SNS as the **event bus** for inbound webhooks. Where the SQS dispatch
queue handles a single, ordered outbound rail (allocator → Twilio), SNS
handles a one-to-many fan-out — a donor reply is interesting to many
downstream subscribers (cooldown, EMA, allocator re-fire, caregiver notify).

Mirror of ``app.integrations.sqs_client`` — same dataclass shape, same
mock-mode behaviour. Topics auto-provision on first publish.

TOPIC NAMING
------------
{prefix}-{topic_name}      e.g. team019-bridge-os-donor-reply-accept

MOCK MODE
---------
Topics in mock mode are an in-memory dict ``topic_name -> list[dict]`` of
historical publishes. The in-process Event Bus drains the list each tick.
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
    topic_name: str
    topic_arn: Optional[str] = None


@dataclass(frozen=True)
class Event:
    """One published message + metadata. Subscribers consume these."""

    message_id: str
    topic_name: str
    body: dict
    published_at: float  # unix seconds (matches Date.now()/1000)
    is_mock: bool


# ---------------------------------------------------------------------------
# Mock backend
# ---------------------------------------------------------------------------


@dataclass
class _MockTopic:
    history: deque = field(default_factory=lambda: deque(maxlen=500))
    lock: threading.Lock = field(default_factory=threading.Lock)


_MOCK_TOPICS: dict[str, _MockTopic] = {}
_MOCK_LOCK = threading.Lock()


def _get_mock_topic(name: str) -> _MockTopic:
    with _MOCK_LOCK:
        return _MOCK_TOPICS.setdefault(name, _MockTopic())


def _reset_mock_topics_for_tests() -> None:
    with _MOCK_LOCK:
        _MOCK_TOPICS.clear()


# ---------------------------------------------------------------------------
# Topic naming
# ---------------------------------------------------------------------------


def full_topic_name(short_name: str) -> str:
    return f"{resource_prefix()}-{short_name}"


# ---------------------------------------------------------------------------
# Topic ARN cache (live mode)
# ---------------------------------------------------------------------------


_TOPIC_ARN_CACHE: dict[str, str] = {}
_TOPIC_ARN_LOCK = threading.Lock()


def _ensure_topic_exists(topic_name: str) -> str:
    """Create the topic if missing, return its ARN. Tags on creation."""
    full = full_topic_name(topic_name) if not topic_name.startswith(resource_prefix()) else topic_name
    with _TOPIC_ARN_LOCK:
        if full in _TOPIC_ARN_CACHE:
            return _TOPIC_ARN_CACHE[full]

    client = get_boto3_client("sns", region=get_region())
    try:
        resp = client.create_topic(
            Name=full,
            Tags=resource_tags() + [{"Key": "Type", "Value": "events"}],
        )
        arn = resp["TopicArn"]
    except Exception:  # pragma: no cover
        logger.exception("create_topic failed for %s", full)
        raise

    with _TOPIC_ARN_LOCK:
        _TOPIC_ARN_CACHE[full] = arn
    return arn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def publish(topic_name: str, body: dict, *, attributes: Optional[dict] = None) -> PublishResult:
    """Publish a JSON body onto a topic. Returns the SNS MessageId."""
    full = full_topic_name(topic_name) if not topic_name.startswith(resource_prefix()) else topic_name
    payload = json.dumps(body, default=str)

    if not aws_available():
        mq = _get_mock_topic(full)
        mid = "MOCK-SNS-" + secrets.token_hex(8).upper()
        with mq.lock:
            mq.history.append(
                Event(
                    message_id=mid,
                    topic_name=full,
                    body=body,
                    published_at=time.time(),
                    is_mock=True,
                )
            )
        return PublishResult(message_id=mid, is_mock=True, topic_name=full)

    try:
        client = get_boto3_client("sns", region=get_region())
        arn = _ensure_topic_exists(full)
        resp = client.publish(
            TopicArn=arn,
            Message=payload,
            MessageAttributes={
                k: {"DataType": "String", "StringValue": str(v)}
                for k, v in (attributes or {}).items()
            },
        )
        # Also record in the in-process history so the events feed UI sees
        # live publishes even when subscribers are remote.
        mq = _get_mock_topic(full)
        with mq.lock:
            mq.history.append(
                Event(
                    message_id=resp.get("MessageId", "UNKNOWN"),
                    topic_name=full,
                    body=body,
                    published_at=time.time(),
                    is_mock=False,
                )
            )
        return PublishResult(
            message_id=resp.get("MessageId", "UNKNOWN"),
            is_mock=False,
            topic_name=full,
            topic_arn=arn,
        )
    except Exception:  # pragma: no cover
        logger.exception("SNS publish failed to %s", full)
        return PublishResult(
            message_id="FAIL-" + secrets.token_hex(8).upper(),
            is_mock=True,
            topic_name=full,
        )


def find_event(message_id: str) -> Optional[Event]:
    """Search the in-process publish history for a specific message id.

    Used by ``POST /system/events/republish/{id}``. In live mode this works
    because every successful ``publish()`` also appends to ``_MOCK_TOPICS``
    so the events feed has the body to render.
    """
    with _MOCK_LOCK:
        topics = list(_MOCK_TOPICS.items())
    for _, mq in topics:
        with mq.lock:
            for ev in mq.history:
                if ev.message_id == message_id:
                    return ev
    return None


def republish_event(message_id: str) -> Optional[PublishResult]:
    """Re-publish an event by id. Returns the new PublishResult or None
    if the event isn't in the history (e.g. older than 500 events ago)."""
    ev = find_event(message_id)
    if ev is None:
        return None
    # The topic_name in the Event is the FULL prefixed name; publish()
    # detects that and skips re-prefixing.
    return publish(ev.topic_name, ev.body)


def recent_events(*, topic_name: Optional[str] = None, limit: int = 50) -> list[Event]:
    """Return the most recent events across all topics (or one topic) — used
    by the in-process subscriber loop AND by the /system/events/recent API."""
    out: list[Event] = []
    if topic_name is not None:
        full = full_topic_name(topic_name) if not topic_name.startswith(resource_prefix()) else topic_name
        mq = _get_mock_topic(full)
        with mq.lock:
            out.extend(list(mq.history))
    else:
        with _MOCK_LOCK:
            topics = list(_MOCK_TOPICS.items())
        for _, mq in topics:
            with mq.lock:
                out.extend(list(mq.history))
    out.sort(key=lambda e: e.published_at, reverse=True)
    return out[:limit]
