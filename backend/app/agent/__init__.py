"""Multilingual LLM Care Agent.

The agent is the natural-language interface to everything Bridge OS knows.
It accepts a query (in any of 8 Indian languages) plus optional entity
context (donor/bridge/patient) and returns an answer plus the structured
"sources" it consulted.

The LLM is hot-pluggable:
    1. BEDROCK_REGION    -> AWS Bedrock multi-model (Sonnet chat + Haiku intent + Titan v2 embeddings)
    2. ANTHROPIC_API_KEY -> Anthropic Claude direct (portable fallback)
    3. neither           -> rule-based mock that still demos every code path

Memory = per-entity context blob assembled fresh on each turn. No vector
store needed for the local demo; pgvector embeddings are straightforward to
add for production (Postgres branch).
"""

from app.agent.embeddings import embed, get_active_provider as embed_provider
from app.agent.engine import answer_query
from app.agent.llm_client import LLMResponse, get_active_provider, is_live
from app.agent.context import (
    AgentContext,
    build_bridge_context,
    build_donor_context,
    build_patient_context,
)
from app.agent.memory import (
    RetrievedMemory,
    list_memories,
    record_memory,
    retrieve_memories,
)

__all__ = [
    "answer_query",
    "is_live",
    "get_active_provider",
    "embed",
    "embed_provider",
    "AgentContext",
    "build_donor_context",
    "build_bridge_context",
    "build_patient_context",
    "LLMResponse",
    "RetrievedMemory",
    "record_memory",
    "retrieve_memories",
    "list_memories",
]
