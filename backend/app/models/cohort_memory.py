"""Episodic cohort memory — the RAG store the Care Agent reads from.

Each row is a short note ("Priya marked at risk after 120 days inactive")
attached to a donor/bridge/patient + a dense embedding. At query time the
agent embeds the user's question, scores cosine similarity against rows
optionally filtered by entity, and prepends the top-K to its prompt.

The embedding column is JSON for portability — works the same on SQLite
and Postgres. To swap to native pgvector, change the column to
`Vector(dim)` and update `app/agent/memory.py::_score()` to use an SQL
similarity operator instead of in-Python cosine. The retrieval API and
schemas don't change.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import GUID


class MemoryKind(str, Enum):
    DONOR = "donor"
    BRIDGE = "bridge"
    PATIENT = "patient"
    WA_THREAD = "wa_thread"
    AGENT_QA = "agent_qa"
    RECRUIT = "recruit"


class CohortMemory(Base):
    """One episodic memory with its embedding."""

    __tablename__ = "cohort_memories"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    kind: Mapped[MemoryKind] = mapped_column(String(20), index=True)

    # Entity the memory is "about" — donor / bridge / patient. Nullable for
    # cross-entity memories (rare).
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True, index=True)

    # Short human-readable note. Kept under ~300 chars to keep embeddings tight.
    summary: Mapped[str] = mapped_column(Text)

    # Embedding vector stored as a JSON list of floats. Cross-dialect.
    embedding: Mapped[list[float]] = mapped_column(JSON)

    # Embedding provider metadata (so we know to re-embed when models change)
    embedding_provider: Mapped[str] = mapped_column(String(32), default="local")
    embedding_dim: Mapped[int] = mapped_column(default=128)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
