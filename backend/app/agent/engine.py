"""Care-agent orchestrator — assembles context, calls the LLM (or mock), returns answer + sources."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.agent.context import (
    AgentContext,
    ContextSource,
    build_bridge_context,
    build_donor_context,
    build_patient_context,
)
from app.agent.language import detect_language
from app.agent.llm_client import ChatMessage, LLMResponse, chat
from app.agent.memory import RetrievedMemory, record_memory, retrieve_memories
from app.models.cohort_memory import MemoryKind


LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi (हिन्दी)",
    "te": "Telugu (తెలుగు)",
    "ta": "Tamil (தமிழ்)",
    "mr": "Marathi (मराठी)",
    "bn": "Bengali (বাংলা)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "gu": "Gujarati (ગુજરાતી)",
}


@dataclass
class AgentResult:
    answer: str
    sources: list[ContextSource]
    provider: str
    model: str
    language: str
    detected_language: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    retrieved_memories: list[RetrievedMemory] | None = None
    task: str | None = None  # Bedrock routing task that selected the model


def _build_context(
    db: Session,
    donor_id: Optional[uuid.UUID],
    bridge_id: Optional[uuid.UUID],
    patient_id: Optional[uuid.UUID],
) -> AgentContext:
    if donor_id is not None:
        return build_donor_context(db, donor_id)
    if bridge_id is not None:
        return build_bridge_context(db, bridge_id)
    if patient_id is not None:
        return build_patient_context(db, patient_id)
    return AgentContext(
        summary=(
            "(No entity selected — answer from general knowledge about Bridge OS: "
            "AI for thalassemia transfusion coordination, donor cohorts of 8–10, "
            "transfusion cadence 18 days, channels = WhatsApp + dashboards.)"
        )
    )


def _build_system_prompt(language: str, has_context: bool) -> str:
    lang_label = LANGUAGE_NAMES.get(language, "English")
    parts = [
        "You are the Bridge OS Care Agent — the LLM that helps blood-bridge",
        "coordinators understand their cohorts and decide what to do next.",
        "Bridge OS is software for the Blood Warriors Foundation, which runs",
        "Blood Bridges: small fixed cohorts of voluntary donors that recur-",
        "donate for one thalassemia patient over many years.",
        "",
        f"Respond in {lang_label}. Be concise — 2 to 4 short paragraphs at most.",
        "Use plain prose; avoid markdown tables. Quote specific names + numbers",
        "from the context, never invent. If asked to take an action you cannot",
        "(e.g. actually send a WhatsApp), describe exactly what the coordinator",
        "should click in the dashboard.",
    ]
    if has_context:
        parts.append("")
        parts.append("The CONTEXT block below was assembled from live database state")
        parts.append("just now — trust it as ground truth.")
    return "\n".join(parts)


def _mock_responder(system: str, messages: list[ChatMessage]) -> str:
    """Rule-based stand-in when no LLM key is configured.

    Lean on the context block + simple intent matching. Good enough that the
    demo flows end-to-end without an API key.
    """
    user_msg = messages[-1].content if messages else ""

    # Extract CONTEXT and QUESTION separately — intent matches only against
    # the question, never against the context (which may contain keywords like
    # "transfusion" / "schedule" that would otherwise hijack every reply).
    ctx_match = re.search(r"CONTEXT:\n(.*?)(?:\n\nQUESTION:|\Z)", user_msg, re.DOTALL)
    ctx = ctx_match.group(1).strip() if ctx_match else ""
    q_match = re.search(r"QUESTION:\s*(.*)\Z", user_msg, re.DOTALL)
    question = (q_match.group(1) if q_match else user_msg).strip()
    user_lower = question.lower()

    # No-entity case (or absent CONTEXT) → capability blurb
    no_entity = (not ctx) or ctx.startswith("(No entity selected")
    if no_entity:
        return (
            "I'm the Bridge OS Care Agent. Ask me about any donor, bridge, or "
            "patient — once you pick an entity from the chip row above, I can "
            "explain stability risks, suggest replacements, or draft a WhatsApp."
        )

    # Pull a couple useful lines from the context
    name = _extract_field(ctx, ["Name:"])
    bg = _extract_field(ctx, ["Blood group:"])
    response_rate = _extract_field(ctx, ["Response rate:"])
    total = _extract_field(ctx, ["Total donations:"])
    last = _extract_field(ctx, ["Last donation:"])

    # Intent: WHY (risk explanation)
    if any(k in user_lower for k in ("why", "risk", "at risk", "weak", "churn")):
        return (
            f"{name or 'This donor'} shows reduced engagement signals — "
            f"response rate {response_rate or 'unknown'}, "
            f"last donation {last or 'unknown'}, and {total or '0'} total donations. "
            "The stability model treats long gaps + slow replies as leading indicators "
            "of churn, so they surface as 'at risk' even though they haven't formally exited. "
            "Open Recommendations to see the ranked replacement candidates."
        )

    # Intent: RECRUIT / REPLACE / SUGGEST
    if any(k in user_lower for k in ("recruit", "replace", "suggest", "candidate", "who should")):
        return (
            "Use Recommendations or the Cohort Simulator to see ranked replacement "
            "candidates for this bridge. The composite score is 30% distance + 30% "
            "response rate + 40% predicted 90-day churn (lower is better), with a "
            "+10% boost when the candidate is Kell-negative. The top 3 typically "
            "score 85+ and are within 5 km of the patient's hospital."
        )

    # Intent: SCHEDULE / NEXT
    if any(k in user_lower for k in ("schedule", "next", "when", "transfusion", "rotation")):
        return (
            "Open Schedule on the bridge page to see the rotation solved by the "
            "OR-Tools CP-SAT solver. Each transfusion in the 365-day horizon is "
            "assigned to one donor under 90-day deferral + cadence constraints. The "
            "solver minimises distance + (1 − response_rate) so reliable nearby "
            "donors carry the load."
        )

    # Intent: MESSAGE / SEND / THANK YOU
    if any(k in user_lower for k in ("send", "message", "whatsapp", "thank", "remind", "draft")):
        return (
            f"Go to WhatsApp, pick {name or 'the donor'}, and choose a template — "
            "Slot reminder, Recruit invite, Thank you, or Swap request. The template "
            "fills the donor + patient name automatically. With TWILIO_* env vars set, "
            "it sends a real WhatsApp; without them it stores a mock message that "
            "still appears in the thread."
        )

    # Intent: SUMMARY / HOW IS
    if any(k in user_lower for k in ("summary", "summarize", "summarise", "status", "how is", "tell me about")):
        if "BRIDGE:" in ctx:
            return (
                "This bridge is loaded — the cohort, patient profile, and recent "
                "scheduling state are all in context. Active donors are listed "
                f"above with their response rates and donation counts. {name or 'The patient'} "
                "is on the standard 18-day cadence. Use the Stability panel on the "
                "bridge page for ML churn predictions per donor."
            )
        return (
            f"{name or 'This donor'} — {bg or '?'}, response rate {response_rate or 'unknown'}, "
            f"{total or '0'} donations total, last on {last or 'unknown'}. "
            "Open the donor's detail page for full bridge memberships + WhatsApp history."
        )

    # Default catchall — light reflection
    return (
        f"I see context for {name or 'the selected entity'}. "
        "Ask me a specific question — e.g. \"why is this donor at risk?\", "
        "\"who should replace them?\", \"when's the next transfusion?\", or "
        "\"draft a thank-you message in Hindi\"."
    )


def _extract_field(ctx: str, keys: list[str]) -> str | None:
    for line in ctx.splitlines():
        for k in keys:
            if k in line:
                return line.split(k, 1)[1].strip()
    return None


def _primary_entity(
    donor_id: Optional[uuid.UUID],
    bridge_id: Optional[uuid.UUID],
    patient_id: Optional[uuid.UUID],
) -> Optional[uuid.UUID]:
    return donor_id or bridge_id or patient_id


def _record_qa_memory(
    db: Session,
    *,
    question: str,
    answer: str,
    entity_id: Optional[uuid.UUID],
) -> None:
    """Persist the Q&A as an episodic memory so the next turn can recall it."""
    summary = f"Q: {question[:120]}\nA: {answer[:240]}"
    try:
        record_memory(
            db,
            kind=MemoryKind.AGENT_QA,
            entity_id=entity_id,
            summary=summary,
        )
    except Exception:
        # Memory recording is best-effort — don't fail the chat turn on it.
        db.rollback()


def answer_query(
    db: Session,
    query: str,
    *,
    donor_id: Optional[uuid.UUID] = None,
    bridge_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None,
    language: str = "en",
    auto_detect: bool = True,
    history: Optional[list[ChatMessage]] = None,
    use_memory: bool = True,
    record_qa: bool = True,
    memory_top_k: int = 4,
) -> AgentResult:
    """Top-level: query in, answer + sources out.

    `language` is the caller's UI preference (default "en"). When `auto_detect`
    is True, we run a script-based detector on `query` — if it sees Indic
    characters it overrides the preference (typing in Telugu = answer in
    Telugu, even if the picker says English). Pure-Latin queries keep the
    caller's `language`.

    Cohort memory:
      - `use_memory=True` retrieves the top-K relevant past memories for the
        current entity and prepends them to the LLM prompt as MEMORIES.
      - `record_qa=True` persists this Q&A as a new memory after the turn.
    """
    ctx = _build_context(db, donor_id, bridge_id, patient_id)

    detected: str | None = None
    if auto_detect:
        detected_code = detect_language(query, fallback=language)  # type: ignore[arg-type]
        if detected_code != language:
            detected = detected_code
            language = detected_code

    has_context = ctx.donor_id is not None or ctx.bridge_id is not None or ctx.patient_id is not None
    system = _build_system_prompt(language, has_context)

    primary_entity = _primary_entity(donor_id, bridge_id, patient_id)
    retrieved: list[RetrievedMemory] = []
    if use_memory:
        retrieved = retrieve_memories(
            db,
            query,
            entity_id=primary_entity,
            top_k=memory_top_k,
        )

    # Build prompt: MEMORIES (if any) → CONTEXT → QUESTION
    parts: list[str] = []
    if retrieved:
        memory_block = "\n".join(
            f"  - [{m.kind} · sim={m.score:.2f}] {m.summary}" for m in retrieved
        )
        parts.append(
            "MEMORIES (most relevant past notes — may include earlier Q&A, "
            f"recruit events, WhatsApp summaries):\n{memory_block}"
        )
    parts.append(f"CONTEXT:\n{ctx.summary}")
    parts.append(f"QUESTION: {query}")
    user_content = "\n\n".join(parts)

    msgs: list[ChatMessage] = list(history or [])
    msgs.append(ChatMessage(role="user", content=user_content))

    # Main user-facing reply uses the "chat" task → Sonnet on Bedrock.
    llm: LLMResponse = chat(
        system_prompt=system,
        messages=msgs,
        max_tokens=1024,
        temperature=0.3,
        task="chat",
        mock_handler=_mock_responder,
    )

    # Stitch retrieved memories into the sources list so the UI can cite them.
    sources = list(ctx.sources)
    for m in retrieved:
        sources.append(
            ContextSource(
                kind=f"memory:{m.kind}",
                label=f"Memory: {m.summary[:60]}{'…' if len(m.summary) > 60 else ''}",
                detail=f"cosine={m.score:.3f}",
            )
        )

    if record_qa:
        _record_qa_memory(
            db,
            question=query,
            answer=llm.text,
            entity_id=primary_entity,
        )

    return AgentResult(
        answer=llm.text,
        sources=sources,
        provider=llm.provider,
        model=llm.model,
        language=language,
        detected_language=detected,
        tokens_in=llm.tokens_in,
        tokens_out=llm.tokens_out,
        retrieved_memories=retrieved,
        task=llm.task,
    )
