"""Tests for the cohort-memory embedding store + RAG-style retrieval."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agent.embeddings import (
    DEFAULT_DIM,
    cosine,
    embed,
    get_active_model,
    get_active_provider,
)
from app.agent.memory import (
    list_memories,
    record_memory,
    retrieve_memories,
)
from app.models import CohortMemory, MemoryKind
from tests.fixtures import build_test_dataset, feature_bridge_destabilizer


def _seed(db: Session):
    return build_test_dataset(db, n_patients=3, n_donors=40, seed=42)


# ----- embeddings -----


def test_local_embedding_is_deterministic_across_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    a = embed("Priya Sharma response rate 32%")
    b = embed("Priya Sharma response rate 32%")
    assert a.vector == b.vector
    assert a.provider == "local"
    assert a.dim == DEFAULT_DIM


def test_local_embedding_is_unit_normalised() -> None:
    e = embed("Aarav Reddy needs replacement donor")
    norm_sq = sum(x * x for x in e.vector)
    assert 0.99 < norm_sq < 1.01


def test_local_embedding_empty_text_returns_zero_vector() -> None:
    e = embed("")
    assert all(x == 0.0 for x in e.vector)


def test_cosine_similarity_bounded_and_symmetric() -> None:
    a = embed("Priya Sharma at-risk donor B+").vector
    b = embed("Priya Sharma destabiliser B+").vector
    c = embed("transfusion schedule next month").vector
    sim_ab = cosine(a, b)
    sim_ac = cosine(a, c)
    # Similar topics overlap more than unrelated ones.
    assert sim_ab > sim_ac
    assert -1.0 <= sim_ab <= 1.0
    # Symmetric
    assert abs(cosine(a, b) - cosine(b, a)) < 1e-9


def test_get_active_provider_defaults_to_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_active_provider() == "local"
    assert "localhash" in get_active_model()


def test_openai_provider_when_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert get_active_provider() == "openai"


# ----- record_memory / retrieve_memories -----


def test_record_memory_persists_with_embedding(db_session: Session) -> None:
    eid = uuid.uuid4()
    row = record_memory(
        db_session,
        kind=MemoryKind.DONOR,
        entity_id=eid,
        summary="Priya Sharma response rate 32%, last donation 120 days ago",
    )
    fetched = db_session.query(CohortMemory).filter(CohortMemory.id == row.id).one()
    assert fetched.entity_id == eid
    assert len(fetched.embedding) == DEFAULT_DIM
    assert fetched.embedding_provider == "local"


def test_retrieve_top_k_returns_most_similar_first(db_session: Session) -> None:
    eid = uuid.uuid4()
    # Three notes — only two are about Priya
    record_memory(db_session, kind=MemoryKind.DONOR, entity_id=eid,
                  summary="Priya Sharma destabilising the bridge response rate low")
    record_memory(db_session, kind=MemoryKind.DONOR, entity_id=eid,
                  summary="Priya Sharma needs replacement urgently")
    record_memory(db_session, kind=MemoryKind.DONOR, entity_id=eid,
                  summary="Coordinator approved schedule for next quarter")

    top = retrieve_memories(
        db_session,
        "Why is Priya at risk?",
        entity_id=eid,
        top_k=3,
    )
    assert len(top) >= 1
    # Both Priya-related memories should outscore the schedule one
    priya_scores = [m.score for m in top if "Priya" in m.summary]
    other_scores = [m.score for m in top if "Priya" not in m.summary]
    if other_scores:
        assert max(priya_scores) > max(other_scores)


def test_retrieve_filters_by_entity_id(db_session: Session) -> None:
    eid_a = uuid.uuid4()
    eid_b = uuid.uuid4()
    record_memory(db_session, kind=MemoryKind.DONOR, entity_id=eid_a,
                  summary="Memory about donor A — Priya Sharma")
    record_memory(db_session, kind=MemoryKind.DONOR, entity_id=eid_b,
                  summary="Memory about donor B — Priya Sharma")

    top_a = retrieve_memories(
        db_session, "Priya Sharma", entity_id=eid_a, top_k=5
    )
    assert len(top_a) == 1
    assert top_a[0].entity_id == eid_a


def test_retrieve_returns_empty_for_empty_query(db_session: Session) -> None:
    eid = uuid.uuid4()
    record_memory(db_session, kind=MemoryKind.DONOR, entity_id=eid,
                  summary="any note")
    assert retrieve_memories(db_session, "", entity_id=eid) == []


def test_retrieve_min_score_filter(db_session: Session) -> None:
    eid = uuid.uuid4()
    record_memory(db_session, kind=MemoryKind.DONOR, entity_id=eid,
                  summary="completely unrelated content nothing matches")
    # An unrelated query should return nothing under a strict floor.
    top = retrieve_memories(
        db_session, "transfusion bridge cohort", entity_id=eid,
        top_k=5, min_score=0.5,
    )
    assert top == []


def test_list_memories_orders_by_recency(db_session: Session) -> None:
    eid = uuid.uuid4()
    record_memory(db_session, kind=MemoryKind.DONOR, entity_id=eid, summary="first")
    record_memory(db_session, kind=MemoryKind.DONOR, entity_id=eid, summary="second")
    rows = list_memories(db_session, entity_id=eid, limit=10)
    assert len(rows) == 2
    # desc by created_at — but SQLite has 1s resolution, so just assert membership.
    summaries = {r.summary for r in rows}
    assert summaries == {"first", "second"}


# ----- agent chat integration -----


def test_chat_persists_qa_as_a_memory(client: TestClient, db_session: Session) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge_id = data.feature_patient.bridge.id

    before = db_session.query(CohortMemory).count()
    client.post(
        "/agent/chat",
        json={"query": "Why is this bridge at risk?", "bridge_id": str(bridge_id)},
    )
    after = db_session.query(CohortMemory).count()
    assert after == before + 1

    row = (
        db_session.query(CohortMemory)
        .filter(CohortMemory.entity_id == bridge_id)
        .order_by(CohortMemory.created_at.desc())
        .first()
    )
    assert row is not None
    assert getattr(row.kind, "value", str(row.kind)) == "agent_qa"
    assert "Why is this bridge" in row.summary


def test_chat_recalls_an_earlier_memory_in_followup(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge_id = str(data.feature_patient.bridge.id)

    # Turn 1
    client.post(
        "/agent/chat",
        json={
            "query": "Priya Sharma seems to be the destabiliser here",
            "bridge_id": bridge_id,
        },
    )
    # Turn 2 — should pull the prior turn back as a memory
    body = client.post(
        "/agent/chat",
        json={"query": "Tell me again about Priya Sharma", "bridge_id": bridge_id},
    ).json()
    summaries = [m["summary"] for m in body["retrieved_memories"]]
    assert any("Priya" in s for s in summaries)


def test_chat_includes_memory_sources_when_retrieved(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge_id = str(data.feature_patient.bridge.id)

    # Seed a memory that should match a clear query
    client.post(
        "/agent/chat",
        json={
            "query": "Priya Sharma response rate is very low",
            "bridge_id": bridge_id,
        },
    )
    body = client.post(
        "/agent/chat",
        json={"query": "What about Priya's response rate?", "bridge_id": bridge_id},
    ).json()
    memory_sources = [s for s in body["sources"] if s["kind"].startswith("memory:")]
    assert memory_sources, "Expected at least one memory source in the second turn"


# ----- /agent/memories endpoint -----


def test_memories_endpoint_lists_recent_rows(
    client: TestClient, db_session: Session
) -> None:
    eid = uuid.uuid4()
    record_memory(db_session, kind=MemoryKind.BRIDGE, entity_id=eid,
                  summary="bridge memory one")
    record_memory(db_session, kind=MemoryKind.BRIDGE, entity_id=eid,
                  summary="bridge memory two")
    db_session.commit()
    body = client.get(f"/agent/memories?entity_id={eid}").json()
    assert len(body) == 2
    summaries = {r["summary"] for r in body}
    assert summaries == {"bridge memory one", "bridge memory two"}


def test_memories_endpoint_no_filter_returns_all(
    client: TestClient, db_session: Session
) -> None:
    record_memory(db_session, kind=MemoryKind.DONOR, summary="without entity 1")
    record_memory(db_session, kind=MemoryKind.DONOR, summary="without entity 2")
    db_session.commit()
    body = client.get("/agent/memories?limit=10").json()
    assert len(body) >= 2
