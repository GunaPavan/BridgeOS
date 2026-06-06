"""Care Agent API — Phase 11."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.agent import (
    answer_query,
    embed_provider,
    get_active_provider,
    is_live,
    list_memories,
)
from app.agent.embeddings import get_active_model as get_embed_model
from app.agent.engine import LANGUAGE_NAMES
from app.agent.llm_client import (
    ChatMessage,
    get_bedrock_model_for_task,
    get_default_model,
)
from app.db import get_db
from app.models import AgentMessage, AgentMessageRole
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentMessageOut,
    AgentSessionSummary,
    AgentStatusOut,
    CohortMemoryOut,
    ContextSourceOut,
    RetrievedMemoryOut,
)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/status", response_model=AgentStatusOut, summary="Active LLM provider")
def get_status() -> AgentStatusOut:
    provider = get_active_provider()
    is_bedrock = provider == "bedrock"
    return AgentStatusOut(
        is_live=is_live(),
        provider=provider,
        model=get_default_model(),
        supported_languages=list(LANGUAGE_NAMES.keys()),  # type: ignore[arg-type]
        multi_model=is_bedrock,
        chat_model=get_bedrock_model_for_task("chat") if is_bedrock else None,
        intent_model=get_bedrock_model_for_task("intent") if is_bedrock else None,
        embedding_model=get_embed_model() if is_bedrock else None,
    )


@router.post(
    "/chat",
    response_model=AgentChatResponse,
    summary="Ask the agent a question; returns answer + sources",
)
def chat_endpoint(
    payload: AgentChatRequest,
    db: Session = Depends(get_db),
) -> AgentChatResponse:
    session_id = payload.session_id or uuid.uuid4()

    # Pull prior history if resuming
    history: list[ChatMessage] = []
    if payload.session_id is not None:
        prior = (
            db.execute(
                select(AgentMessage)
                .where(AgentMessage.session_id == payload.session_id)
                .order_by(AgentMessage.created_at)
            )
            .scalars()
            .all()
        )
        for m in prior:
            role_val = getattr(m.role, "value", str(m.role))
            if role_val in ("user", "assistant"):
                history.append(
                    ChatMessage(role=role_val, content=m.content)  # type: ignore[arg-type]
                )

    result = answer_query(
        db,
        payload.query,
        donor_id=payload.donor_id,
        bridge_id=payload.bridge_id,
        patient_id=payload.patient_id,
        language=payload.language,
        history=history,
    )

    # If the engine auto-detected a different language, persist the effective one.
    effective_language = result.language
    user_row = AgentMessage(
        session_id=session_id,
        role=AgentMessageRole.USER,
        content=payload.query,
        donor_id=payload.donor_id,
        bridge_id=payload.bridge_id,
        patient_id=payload.patient_id,
        language=effective_language,
    )
    assistant_row = AgentMessage(
        session_id=session_id,
        role=AgentMessageRole.ASSISTANT,
        content=result.answer,
        donor_id=payload.donor_id,
        bridge_id=payload.bridge_id,
        patient_id=payload.patient_id,
        language=effective_language,
        provider=result.provider,
        model=result.model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        task=getattr(result, "task", None),
    )
    db.add(user_row)
    db.add(assistant_row)
    db.commit()
    db.refresh(user_row)
    db.refresh(assistant_row)

    return AgentChatResponse(
        session_id=session_id,
        user_message=AgentMessageOut.model_validate(user_row),
        assistant_message=AgentMessageOut.model_validate(assistant_row),
        sources=[
            ContextSourceOut(kind=s.kind, label=s.label, detail=s.detail)
            for s in result.sources
        ],
        provider=result.provider,
        model=result.model,
        is_live=result.provider != "mock",
        language=effective_language,  # type: ignore[arg-type]
        detected_language=result.detected_language,  # type: ignore[arg-type]
        retrieved_memories=[
            RetrievedMemoryOut(
                id=m.id,
                kind=m.kind,
                entity_id=m.entity_id,
                summary=m.summary,
                score=m.score,
            )
            for m in (result.retrieved_memories or [])
        ],
        task=getattr(result, "task", None),
    )


@router.get(
    "/memories",
    response_model=list[CohortMemoryOut],
    summary="Inspect stored cohort memories (optionally filtered by entity)",
)
def list_cohort_memories(
    entity_id: uuid.UUID | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[CohortMemoryOut]:
    rows = list_memories(db, entity_id=entity_id, limit=limit)
    return [
        CohortMemoryOut(
            id=r.id,
            kind=getattr(r.kind, "value", str(r.kind)),
            entity_id=r.entity_id,
            summary=r.summary,
            embedding_provider=r.embedding_provider,
            embedding_dim=r.embedding_dim,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get(
    "/sessions",
    response_model=list[AgentSessionSummary],
    summary="List recent agent sessions",
)
def list_sessions(
    limit: int = 20,
    db: Session = Depends(get_db),
) -> list[AgentSessionSummary]:
    agg = (
        select(
            AgentMessage.session_id,
            func.min(AgentMessage.created_at).label("first_at"),
            func.max(AgentMessage.created_at).label("last_at"),
            func.count(AgentMessage.id).label("msg_count"),
        )
        .group_by(AgentMessage.session_id)
        .order_by(desc("last_at"))
        .limit(limit)
        .subquery()
    )
    rows = db.execute(select(agg)).all()

    summaries: list[AgentSessionSummary] = []
    for r in rows:
        # First user message in session = description
        first_user = (
            db.execute(
                select(AgentMessage)
                .where(
                    AgentMessage.session_id == r.session_id,
                    AgentMessage.role == AgentMessageRole.USER.value,
                )
                .order_by(AgentMessage.created_at)
                .limit(1)
            )
            .scalars()
            .first()
        )
        last_lang = (
            db.execute(
                select(AgentMessage.language)
                .where(AgentMessage.session_id == r.session_id)
                .order_by(desc(AgentMessage.created_at))
                .limit(1)
            )
            .scalars()
            .first()
        )
        summaries.append(
            AgentSessionSummary(
                session_id=r.session_id,
                first_message_at=r.first_at,
                last_message_at=r.last_at,
                message_count=int(r.msg_count),
                last_user_query=(first_user.content if first_user else "")[:200],
                language=last_lang or "en",
            )
        )
    return summaries


@router.get(
    "/sessions/{session_id}",
    response_model=list[AgentMessageOut],
    summary="Full message history for a session",
)
def get_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[AgentMessageOut]:
    msgs = (
        db.execute(
            select(AgentMessage)
            .where(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.created_at)
        )
        .scalars()
        .all()
    )
    if not msgs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return [AgentMessageOut.model_validate(m) for m in msgs]
