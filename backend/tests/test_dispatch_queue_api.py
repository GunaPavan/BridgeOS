"""Phase E3 — /system/dispatch-queue/* endpoint tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _mock_aws(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    from app.integrations import sqs_client
    sqs_client._reset_mock_queues_for_tests()


def test_status_shape_on_empty_queue(client: TestClient):
    r = client.get("/system/dispatch-queue/status")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "primary_depth", "in_flight", "dlq_depth", "mode",
        "worker_running", "worker_received", "worker_sent",
        "worker_duplicates_skipped", "worker_failed",
    ):
        assert key in body
    assert body["mode"] == "mock"


def test_status_reports_published_messages(client: TestClient):
    from app.integrations import sqs_client
    sqs_client.publish({"x": 1})
    sqs_client.publish({"x": 2})
    body = client.get("/system/dispatch-queue/status").json()
    assert body["primary_depth"] == 2


def test_list_messages_peek(client: TestClient):
    from app.integrations import sqs_client
    sqs_client.publish({"channel": "whatsapp", "to": "+91...", "body": "hi"})
    body = client.get("/system/dispatch-queue/messages?limit=5").json()
    assert len(body) == 1
    assert body[0]["body"]["body"] == "hi"


def test_replay_dlq_empty(client: TestClient):
    body = client.post("/system/dispatch-queue/replay-dlq").json()
    assert body["replayed"] == 0
    assert body["failed"] == 0


def test_replay_dlq_moves_messages(client: TestClient):
    from app.integrations import sqs_client
    dlq = sqs_client.dispatch_dlq_name()
    sqs_client.publish({"x": 1}, queue_name=dlq)
    sqs_client.publish({"x": 2}, queue_name=dlq)
    body = client.post("/system/dispatch-queue/replay-dlq").json()
    assert body["replayed"] == 2


def test_delete_message_removes_poison(client: TestClient):
    from app.integrations import sqs_client
    pr = sqs_client.publish({"x": "poison"})
    # Sanity: it's queued
    assert sqs_client.queue_depth()["primary"] == 1
    r = client.delete(f"/system/dispatch-queue/messages/{pr.message_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["message_id"] == pr.message_id
    assert body["removed"] is True
    assert sqs_client.queue_depth()["primary"] == 0


def test_delete_message_404_when_missing(client: TestClient):
    r = client.delete("/system/dispatch-queue/messages/does-not-exist")
    assert r.status_code == 404


def test_delete_message_also_checks_dlq(client: TestClient):
    from app.integrations import sqs_client
    dlq = sqs_client.dispatch_dlq_name()
    pr = sqs_client.publish({"x": "poison-dlq"}, queue_name=dlq)
    r = client.delete(f"/system/dispatch-queue/messages/{pr.message_id}")
    assert r.status_code == 200
    assert sqs_client.queue_depth()["dlq"] == 0
