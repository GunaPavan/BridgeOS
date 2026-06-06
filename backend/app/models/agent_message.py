"""Persisted chat history for the Care Agent — Phase 11."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import GUID


class AgentMessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AgentMessage(Base):
    """One message in an agent conversation (a "session").

    A session_id ties messages together so the UI can resume a thread; we
    don't model "Session" as its own table — the id is just a UUID generated
    on the first turn.
    """

    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(GUID(), index=True)

    role: Mapped[AgentMessageRole] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)

    # Optional entity context the message was about
    donor_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    bridge_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)

    language: Mapped[str] = mapped_column(String(4), default="en")

    # Provider metadata (for transparency / debugging)
    provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    tokens_in: Mapped[Optional[int]] = mapped_column(nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(nullable=True)
    # Bedrock-only: which routing task chose the model ("chat", "intent", etc.)
    task: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
