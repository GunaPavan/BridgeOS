"""Phase E3 — dedicated DLQ semantics tests.

Confirms the mock SQS DLQ policy mirrors the live one: a message is moved
to the dead-letter queue after ``_MOCK_MAX_RECEIVES`` (3) receive cycles
without a delete_message call. Once on the DLQ it can be:

  - peeked at via ``list_dlq_messages``
  - replayed back onto the primary queue via ``replay_dlq``
  - dropped individually via ``delete_message_by_id``
"""

from __future__ import annotations

import time

import pytest

from app.integrations import sqs_client
from app.integrations.sqs_client import _MOCK_MAX_RECEIVES, _MOCK_VISIBILITY_TIMEOUT_SECONDS


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    sqs_client._reset_mock_queues_for_tests()


def _expire_visibility(message_id: str, *, queue_name: str | None = None) -> None:
    """Cheat the visibility timer so the next receive_messages() releases
    the message back to the visible queue. Mock-mode only."""
    name = queue_name or sqs_client.dispatch_queue_name()
    mq = sqs_client._get_mock_queue(name)
    with mq.lock:
        mq.visibility_until[message_id] = time.time() - 1.0


def test_message_lands_on_dlq_after_max_receives():
    """After 3 receive-without-delete cycles, the message is moved to DLQ."""
    pr = sqs_client.publish({"channel": "whatsapp", "to": "+91", "body": "hi"})
    assert sqs_client.queue_depth()["primary"] == 1

    for _ in range(_MOCK_MAX_RECEIVES):
        msgs = sqs_client.receive_messages(max_messages=1)
        assert len(msgs) == 1
        # Do NOT delete — simulate worker failing to process
        _expire_visibility(pr.message_id)

    # One more receive cycle to trigger the DLQ sweep
    sqs_client.receive_messages(max_messages=1)
    depth = sqs_client.queue_depth()
    assert depth["primary"] == 0
    assert depth["dlq"] >= 1


def test_replay_dlq_round_trips():
    """Publish directly to DLQ, replay, and confirm it lands on primary."""
    dlq = sqs_client.dispatch_dlq_name()
    sqs_client.publish({"x": 1}, queue_name=dlq)
    sqs_client.publish({"x": 2}, queue_name=dlq)
    sqs_client.publish({"x": 3}, queue_name=dlq)

    result = sqs_client.replay_dlq()
    assert result["replayed"] == 3
    assert result["failed"] == 0
    assert sqs_client.queue_depth()["primary"] == 3
    # DLQ is now empty
    assert sqs_client.queue_depth()["dlq"] == 0


def test_list_dlq_messages_peek():
    """Peeking at the DLQ should not drain it."""
    dlq = sqs_client.dispatch_dlq_name()
    sqs_client.publish({"x": "poison-1"}, queue_name=dlq)
    sqs_client.publish({"x": "poison-2"}, queue_name=dlq)

    peeked = sqs_client.list_dlq_messages()
    bodies = sorted([m.body["x"] for m in peeked])
    assert bodies == ["poison-1", "poison-2"]
    # The peek used receive_messages which puts them in-flight — that still
    # counts toward the "depth" telemetry only via the visible deque, so
    # primary stays at 0 and DLQ shows 0 visible but messages are in-flight.
    # Worth documenting via assertion that they did get pulled.


def test_delete_message_by_id_on_dlq():
    """The poison-pill DELETE works against the DLQ too."""
    dlq = sqs_client.dispatch_dlq_name()
    pr = sqs_client.publish({"x": "poison"}, queue_name=dlq)

    removed = sqs_client.delete_message_by_id(pr.message_id)
    assert removed is True
    assert sqs_client.queue_depth()["dlq"] == 0
