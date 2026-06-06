"""Record + retrieve cohort memories. Backed by the `cohort_memories` table.

For ~100-1000 rows per entity (hackathon scale) we score in Python after a
filtered SQL fetch — no pgvector required. Swap to Postgres + pgvector by
changing the column type and using `ORDER BY embedding <-> :q LIMIT k` in
SQL; the public functions in this module stay the same.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.agent.embeddings import cosine, embed
from app.models import CohortMemory
from app.models.cohort_memory import MemoryKind


@dataclass
class RetrievedMemory:
    id: uuid.UUID
    kind: str
    entity_id: Optional[uuid.UUID]
    summary: str
    score: float  # cosine similarity to query


def record_memory(
    db: Session,
    *,
    kind: MemoryKind,
    summary: str,
    entity_id: Optional[uuid.UUID] = None,
    commit: bool = True,
) -> CohortMemory:
    """Embed `summary`, persist a row, return it."""
    e = embed(summary)
    row = CohortMemory(
        kind=kind,
        entity_id=entity_id,
        summary=summary,
        embedding=e.vector,
        embedding_provider=e.provider,
        embedding_dim=e.dim,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    return row


def retrieve_memories(
    db: Session,
    query: str,
    *,
    entity_id: Optional[uuid.UUID] = None,
    top_k: int = 5,
    min_score: float = 0.05,
) -> list[RetrievedMemory]:
    """Cosine-rank memories against `query`. Filter to `entity_id` when set.

    Returns up to `top_k` rows with score >= `min_score`, sorted desc.
    """
    if not query.strip():
        return []

    q_vec = embed(query).vector

    stmt = select(CohortMemory)
    if entity_id is not None:
        stmt = stmt.where(CohortMemory.entity_id == entity_id)
    # Pull recent first so dim mismatches (after re-embed) decay gracefully
    stmt = stmt.order_by(desc(CohortMemory.created_at)).limit(500)
    rows = db.execute(stmt).scalars().all()

    scored: list[tuple[float, CohortMemory]] = []
    for r in rows:
        if r.embedding_dim != len(q_vec):
            # Skip mismatched-dim memories (e.g. provider was swapped)
            continue
        s = cosine(q_vec, r.embedding)
        if s >= min_score:
            scored.append((s, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]
    return [
        RetrievedMemory(
            id=r.id,
            kind=getattr(r.kind, "value", str(r.kind)),
            entity_id=r.entity_id,
            summary=r.summary,
            score=s,
        )
        for s, r in top
    ]


def list_memories(
    db: Session,
    *,
    entity_id: Optional[uuid.UUID] = None,
    limit: int = 50,
) -> list[CohortMemory]:
    """Plain list (no scoring) — used by the inspector endpoint."""
    stmt = select(CohortMemory)
    if entity_id is not None:
        stmt = stmt.where(CohortMemory.entity_id == entity_id)
    stmt = stmt.order_by(desc(CohortMemory.created_at)).limit(limit)
    return list(db.execute(stmt).scalars().all())
