"""Integration tests for /agent endpoints + the engine + mock LLM path."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agent import answer_query, get_active_provider, is_live
from app.agent.context import build_bridge_context, build_donor_context
from app.agent.engine import _mock_responder  # type: ignore[attr-defined]
from app.agent.llm_client import ChatMessage
from app.models import AgentMessage, MembershipStatus
from tests.fixtures import build_test_dataset, feature_bridge_destabilizer


def _seed(db: Session):
    return build_test_dataset(db, n_patients=3, n_donors=40, seed=42)


# ----- /agent/status -----


def test_status_reports_mock_mode_by_default(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    body = client.get("/agent/status").json()
    assert body["is_live"] is False
    assert body["provider"] == "mock"
    assert "en" in body["supported_languages"]
    assert len(body["supported_languages"]) == 8


def test_status_reports_anthropic_when_env_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    body = client.get("/agent/status").json()
    assert body["is_live"] is True
    assert body["provider"] == "anthropic"
    assert body["model"].startswith("claude")


# ----- Bedrock multi-model status (Module 1) -----


def test_status_reports_bedrock_when_region_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When BEDROCK_REGION is set, status reports multi-model routing on."""
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    body = client.get("/agent/status").json()
    assert body["provider"] == "bedrock"
    assert body["is_live"] is True
    assert body["multi_model"] is True
    assert body["chat_model"] and "sonnet" in body["chat_model"].lower()
    assert body["intent_model"] and "haiku" in body["intent_model"].lower()
    assert body["embedding_model"] and "titan" in body["embedding_model"].lower()


def test_status_multi_model_false_when_not_bedrock(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-Bedrock providers leave multi_model=False + per-task fields null."""
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    body = client.get("/agent/status").json()
    assert body["multi_model"] is False
    assert body["chat_model"] is None
    assert body["intent_model"] is None
    assert body["embedding_model"] is None


def test_status_bedrock_takes_priority_over_anthropic(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If both BEDROCK_REGION and ANTHROPIC_API_KEY are set, Bedrock wins —
    that's the hackathon-spec preference for the unified AI layer."""
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    body = client.get("/agent/status").json()
    assert body["provider"] == "bedrock"


# ----- /agent/chat without context -----


def test_chat_without_context_returns_capability_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    body = client.post(
        "/agent/chat",
        json={"query": "What can you do?"},
    ).json()
    assert "session_id" in body
    assert body["provider"] == "mock"
    assert body["is_live"] is False
    # Mock without context returns the capability blurb
    assert "Bridge OS" in body["assistant_message"]["content"]


def test_chat_creates_a_new_session_id_if_none_provided(
    client: TestClient,
) -> None:
    body = client.post("/agent/chat", json={"query": "hi"}).json()
    assert uuid.UUID(body["session_id"])


def test_chat_persists_both_user_and_assistant_messages(
    client: TestClient, db_session: Session
) -> None:
    body = client.post("/agent/chat", json={"query": "Test ping"}).json()
    rows = db_session.query(AgentMessage).all()
    assert len(rows) == 2
    roles = {getattr(r.role, "value", str(r.role)) for r in rows}
    assert roles == {"user", "assistant"}


def test_chat_reuse_session_resumes_history(
    client: TestClient, db_session: Session
) -> None:
    first = client.post("/agent/chat", json={"query": "First turn"}).json()
    sid = first["session_id"]
    client.post("/agent/chat", json={"query": "Second turn", "session_id": sid}).json()
    rows = (
        db_session.query(AgentMessage)
        .filter(AgentMessage.session_id == uuid.UUID(sid))
        .all()
    )
    assert len(rows) == 4  # 2 user + 2 assistant


# ----- /agent/chat with bridge context -----




def test_chat_recruit_intent_returns_recommender_guidance(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    body = client.post(
        "/agent/chat",
        json={
            "query": "Who should I recruit to replace her?",
            "bridge_id": str(data.feature_patient.bridge.id),
        },
    ).json()
    assert "Recommendation" in body["assistant_message"]["content"] or "candidate" in body["assistant_message"]["content"].lower()


def test_chat_message_intent_routes_to_whatsapp(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge = data.feature_patient.bridge
    priya = feature_bridge_destabilizer(data)

    body = client.post(
        "/agent/chat",
        json={
            "query": "Draft a thank you message",
            "donor_id": str(priya.id),
        },
    ).json()
    assert "WhatsApp" in body["assistant_message"]["content"]


def test_chat_schedule_intent_mentions_solver(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    body = client.post(
        "/agent/chat",
        json={
            "query": "When is the next transfusion?",
            "bridge_id": str(data.feature_patient.bridge.id),
        },
    ).json()
    assert "OR-Tools" in body["assistant_message"]["content"] or "Schedule" in body["assistant_message"]["content"]


# ----- /agent/chat language -----


def test_chat_records_requested_language(
    client: TestClient, db_session: Session
) -> None:
    body = client.post(
        "/agent/chat",
        json={"query": "Hello", "language": "hi"},
    ).json()
    assert body["user_message"]["language"] == "hi"
    assert body["assistant_message"]["language"] == "hi"


def test_chat_rejects_unsupported_language(client: TestClient) -> None:
    resp = client.post(
        "/agent/chat",
        json={"query": "Hello", "language": "fr"},
    )
    assert resp.status_code == 422


# ----- /agent/sessions -----


def test_sessions_empty_initially(client: TestClient) -> None:
    body = client.get("/agent/sessions").json()
    assert body == []


def test_sessions_lists_distinct_sessions_with_counts(
    client: TestClient,
) -> None:
    # Two distinct sessions
    s1 = client.post("/agent/chat", json={"query": "Session 1 query A"}).json()[
        "session_id"
    ]
    client.post("/agent/chat", json={"query": "Session 1 query B", "session_id": s1})
    client.post("/agent/chat", json={"query": "Session 2 query"})

    sessions = client.get("/agent/sessions").json()
    assert len(sessions) == 2
    for s in sessions:
        assert s["message_count"] >= 2
        assert s["last_user_query"]


def test_get_session_returns_full_history_in_order(
    client: TestClient,
) -> None:
    first = client.post("/agent/chat", json={"query": "Turn one"}).json()
    sid = first["session_id"]
    client.post("/agent/chat", json={"query": "Turn two", "session_id": sid})

    msgs = client.get(f"/agent/sessions/{sid}").json()
    assert len(msgs) == 4
    contents = [m["content"] for m in msgs]
    assert contents[0] == "Turn one"
    assert contents[2] == "Turn two"


def test_get_session_unknown_returns_404(client: TestClient) -> None:
    resp = client.get(f"/agent/sessions/{uuid.uuid4()}")
    assert resp.status_code == 404


# ----- pure-function unit tests -----




def test_answer_query_pure_function_returns_result(db_session: Session) -> None:
    data = _seed(db_session)
    db_session.commit()
    result = answer_query(
        db_session,
        "What is this bridge about?",
        bridge_id=data.feature_patient.bridge.id,
        language="en",
    )
    assert result.answer
    assert result.provider == "mock"
    assert result.language == "en"


def test_mock_responder_detects_risk_intent() -> None:
    msg = ChatMessage(
        role="user",
        content=(
            "CONTEXT:\nName: Priya Sharma\nBlood group: B+\n"
            "Response rate: 32%\nTotal donations: 2\nLast donation: 2026-01-31\n\n"
            "QUESTION: Why is she at risk?"
        ),
    )
    out = _mock_responder("system", [msg])
    assert "Priya Sharma" in out
    assert "32%" in out


def test_mock_responder_falls_back_to_capability_when_no_context() -> None:
    msg = ChatMessage(role="user", content="Hello, what can you do?")
    out = _mock_responder("system", [msg])
    assert "Bridge OS" in out
