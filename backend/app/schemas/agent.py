"""Care Agent request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


LanguageLiteral = Literal["en", "hi", "te", "ta", "mr", "bn", "kn", "gu"]


class AgentStatusOut(BaseModel):
    is_live: bool
    provider: Literal["bedrock", "anthropic", "mock"]
    model: str
    supported_languages: list[LanguageLiteral]
    # Multi-model fields — populated only when provider == "bedrock"
    multi_model: bool = Field(
        default=False,
        description="True when running on Bedrock with task-based model routing.",
    )
    chat_model: Optional[str] = Field(
        default=None,
        description="Bedrock model id used for chat/reasoning tasks (Sonnet).",
    )
    intent_model: Optional[str] = Field(
        default=None,
        description="Bedrock model id used for intent classification (Haiku).",
    )
    embedding_model: Optional[str] = Field(
        default=None,
        description="Bedrock model id used for embeddings (Titan v2).",
    )


class ContextSourceOut(BaseModel):
    kind: str
    label: str
    detail: Optional[str] = None


class AgentChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Pass the same id on subsequent turns to resume a session.",
    )
    donor_id: Optional[uuid.UUID] = None
    bridge_id: Optional[uuid.UUID] = None
    patient_id: Optional[uuid.UUID] = None
    language: LanguageLiteral = "en"


class AgentMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: Literal["user", "assistant", "system"]
    content: str
    donor_id: Optional[uuid.UUID]
    bridge_id: Optional[uuid.UUID]
    patient_id: Optional[uuid.UUID]
    language: str
    provider: Optional[str]
    model: Optional[str]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    task: Optional[str] = Field(
        default=None,
        description=(
            "Which Bedrock routing task handled this turn. 'chat' for "
            "Sonnet (default), 'intent' for Haiku. Null on non-Bedrock providers."
        ),
    )
    created_at: datetime


class RetrievedMemoryOut(BaseModel):
    id: uuid.UUID
    kind: str
    entity_id: Optional[uuid.UUID]
    summary: str
    score: float


class CohortMemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    entity_id: Optional[uuid.UUID]
    summary: str
    embedding_provider: str
    embedding_dim: int
    created_at: datetime


class AgentChatResponse(BaseModel):
    session_id: uuid.UUID
    user_message: AgentMessageOut
    assistant_message: AgentMessageOut
    sources: list[ContextSourceOut]
    provider: str
    model: str
    is_live: bool
    language: LanguageLiteral
    detected_language: Optional[LanguageLiteral] = Field(
        default=None,
        description=(
            "Set when the agent auto-detected a different language from the query "
            "script than the one the caller passed in. Null when no override "
            "happened (Latin text, or detection matched the request)."
        ),
    )
    retrieved_memories: list[RetrievedMemoryOut] = Field(
        default_factory=list,
        description="Top-K cohort memories the agent recalled and used in this answer.",
    )
    task: Optional[str] = Field(
        default=None,
        description="Routing task that selected the model (Bedrock only).",
    )


class AgentSessionSummary(BaseModel):
    session_id: uuid.UUID
    first_message_at: datetime
    last_message_at: datetime
    message_count: int
    last_user_query: str
    language: str
