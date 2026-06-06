"""Phase E3 — SQS client tests (mock + live paths)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_mock_queues(monkeypatch):
    """Each test starts from an empty mock queue."""
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    from app.integrations import sqs_client
    sqs_client._reset_mock_queues_for_tests()
    yield


def test_publish_returns_mock_id_when_no_aws():
    from app.integrations import sqs_client
    res = sqs_client.publish({"channel": "whatsapp", "to": "+91...", "body": "hi"})
    assert res.is_mock is True
    assert res.message_id.startswith("MOCK-SQS-")


def test_publish_then_receive_returns_same_body():
    from app.integrations import sqs_client
    payload = {"channel": "whatsapp", "to": "+91...", "body": "hello"}
    sqs_client.publish(payload)
    msgs = sqs_client.receive_messages()
    assert len(msgs) == 1
    assert msgs[0].body == payload
    assert msgs[0].is_mock


def test_delete_message_removes_from_queue():
    from app.integrations import sqs_client
    sqs_client.publish({"x": 1})
    msgs = sqs_client.receive_messages()
    assert len(msgs) == 1
    assert sqs_client.delete_message(receipt_handle=msgs[0].receipt_handle) is True


def test_queue_depth_reports_pending():
    from app.integrations import sqs_client
    sqs_client.publish({"a": 1})
    sqs_client.publish({"a": 2})
    depth = sqs_client.queue_depth()
    assert depth["primary"] == 2
    assert depth["mode"] == "mock"


def test_visibility_timeout_hides_message_temporarily(monkeypatch):
    """A message that's been received is invisible to subsequent receives
    until its visibility timeout expires (which we don't simulate here —
    just verify it disappears from the next poll without being deleted)."""
    from app.integrations import sqs_client
    sqs_client.publish({"a": 1})
    first = sqs_client.receive_messages()
    assert len(first) == 1
    second = sqs_client.receive_messages()  # still inside visibility window
    assert second == []


def test_dlq_after_max_receives():
    """After _MOCK_MAX_RECEIVES polls without delete, the message is
    moved to the DLQ on the next receive (visibility expires → DLQ check)."""
    from app.integrations import sqs_client
    sqs_client.publish({"poison": True})
    primary = sqs_client.dispatch_queue_name()
    mq = sqs_client._get_mock_queue(primary)

    # Three rounds of: receive → expire visibility immediately so next
    # receive sees the message as eligible. The 4th receive moves it to DLQ.
    for _ in range(sqs_client._MOCK_MAX_RECEIVES + 1):
        sqs_client.receive_messages()
        with mq.lock:
            for k in list(mq.visibility_until.keys()):
                mq.visibility_until[k] = 0  # expire immediately

    # One more receive call to trigger the in-flight sweep that lands it in DLQ
    sqs_client.receive_messages()
    depth = sqs_client.queue_depth()
    assert depth["dlq"] >= 1


def test_replay_dlq_moves_back_to_primary(monkeypatch):
    from app.integrations import sqs_client
    dlq = sqs_client.dispatch_dlq_name()
    sqs_client.publish({"r": 1}, queue_name=dlq)
    sqs_client.publish({"r": 2}, queue_name=dlq)
    result = sqs_client.replay_dlq()
    assert result["replayed"] == 2
    primary_depth = sqs_client.queue_depth()["primary"]
    assert primary_depth == 2


def test_publish_fallback_when_boto3_raises(monkeypatch):
    """In live mode, if SQS API errors, we degrade to in-memory mock so the
    loop doesn't deadlock."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")
    monkeypatch.delenv("BRIDGE_OS_DISABLE_AWS", raising=False)
    from app.integrations import sqs_client

    def _boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(sqs_client, "_ensure_queue_exists", _boom)
    res = sqs_client.publish({"x": 1})
    assert res.is_mock is True
    assert res.message_id.startswith(("MOCK-SQS-", "FAIL-FALLBACK-"))
