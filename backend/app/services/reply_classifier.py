"""Smart inbound-reply classifier.

Turns free-text WhatsApp replies into one of eight ``ReplyIntent`` values
so the automation engine can dispatch the right side-effect. Uses Bedrock
Claude Haiku 4.5 (fast + cheap) with a strict JSON schema response. Falls
back to a multilingual keyword parser if Bedrock errors out — the system
never deadlocks waiting on a model call.

Public entry point:

    classify_reply(text, language="en", context=None) -> ClassifiedReply

The returned dataclass carries the picked intent, the model's confidence,
any extracted structured data (preferred reschedule date, decline reason),
the raw model JSON response (for audit), and a flag indicating whether we
took the fallback path.

Intent semantics (kept short here — see model docstring for the rationale):

    ACCEPT              — donor said yes (including soft "ok, I'll come")
    DECLINE             — donor said no (without specifying medical / OOT)
    RESCHEDULE_REQUEST  — donor wants a different date ("can I come Monday")
    OUT_OF_TOWN         — temporarily unavailable due to location
    MEDICAL_DEFER       — temporarily unavailable due to illness / recent meds
    UNRELATED_QUESTION  — asks about something else (forward to Care Agent)
    STOP                — explicit opt-out request
    UNKNOWN             — couldn't classify, caller should fall back

CONFIDENCE GATE: the webhook only dispatches if confidence ≥ 0.7 AND intent
is not UNKNOWN. Lower-confidence calls fall through to the legacy YES/NO
keyword parser. This is the explicit "interpret responses to guide next
steps" pillar of the problem statement.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from app.models.enums import ReplyIntent
from app.utils import intent as _legacy_intent

logger = logging.getLogger(__name__)


# Confidence threshold below which we treat the result as UNKNOWN regardless
# of what the model returned. Caller falls back to keyword parsing.
CONFIDENCE_THRESHOLD = 0.7

# Anything below this and the auto-side-effect dispatcher refuses to act —
# even at threshold we won't, for example, set a 14-day medical cooldown on
# a wobbly hit.
ACTIONABLE_THRESHOLD = 0.7


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


@dataclass
class ClassifiedReply:
    intent: ReplyIntent
    confidence: float
    extracted_date: Optional[date] = None
    extracted_reason: Optional[str] = None
    model_used: str = ""
    used_fallback: bool = False
    raw_response: str = ""

    @property
    def is_actionable(self) -> bool:
        """True when callers should dispatch the matched side-effect."""
        return (
            self.intent != ReplyIntent.UNKNOWN
            and self.confidence >= ACTIONABLE_THRESHOLD
        )


# ---------------------------------------------------------------------------
# Bedrock prompt
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """You classify SMS/WhatsApp replies from blood donors in India.
The donor was just asked whether they can donate for a thalassemia patient.

Return ONLY a single JSON object — no prose, no markdown fence — with these fields:
  intent      : one of ["accept","decline","reschedule_request","out_of_town",
                       "medical_defer","unrelated_question","stop","unknown"]
  confidence  : float in [0.0, 1.0]
  date        : ISO date "YYYY-MM-DD" if the reply explicitly mentions a
                rescheduled date; otherwise null
  reason      : short string (<= 200 chars) describing the reason if relevant;
                otherwise null

Intent definitions:
  - accept              : willing to donate now (yes, ok, sure, will come, confirm)
  - decline             : unwilling, no reason (no, can't, not interested)
  - reschedule_request  : wants a different date (can I come Sunday instead)
  - out_of_town         : temporarily away (out of town, travelling, on vacation)
  - medical_defer       : sick / on antibiotics / recent medication / under treatment
  - unrelated_question  : asks something else (what blood group, where, payment?)
  - stop                : opt out completely (don't contact me, unsubscribe, stop)
  - unknown             : cannot tell — DO NOT GUESS

Confidence rules:
  - 0.95-1.00 : explicit, unambiguous (yes / no / stop)
  - 0.80-0.94 : clear intent with some interpretation
  - 0.60-0.79 : likely but uncertain
  - < 0.60    : guessing — use unknown instead

Donor messages may be in English, Hindi, Telugu, Tamil, Marathi, Bengali,
Kannada, Gujarati, or transliterated romanised forms. Multiple languages may
mix within a single message. Be tolerant of typos.

Output JSON only. No preamble. No code fence.
"""


def _build_user_prompt(text: str, language: str, context: dict | None) -> str:
    ctx = context or {}
    lines = [f"Donor reply (language hint: {language}):", "", text.strip()]
    if ctx.get("patient_name"):
        lines += ["", f"(They were asked about patient: {ctx['patient_name']})"]
    if ctx.get("slot_date"):
        lines += [f"(For slot on: {ctx['slot_date']})"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Bedrock call (Haiku 4.5 by default)
# ---------------------------------------------------------------------------


def _haiku_model_id() -> str:
    """Bedrock Claude Haiku 4.5 — cheap + fast for classification."""
    return (
        os.environ.get("BEDROCK_HAIKU_ID")
        or "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    )


def _bedrock_region() -> str:
    return os.environ.get("BEDROCK_REGION") or "us-east-1"


def _call_bedrock(text: str, language: str, context: dict | None) -> dict:
    """Return the parsed model JSON. Raises on any failure."""
    import boto3  # type: ignore[import-not-found]

    client = boto3.client("bedrock-runtime", region_name=_bedrock_region())
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 256,
        "temperature": 0.0,  # deterministic — classification, not generation
        "system": _SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": _build_user_prompt(text, language, context)},
        ],
    }
    response = client.invoke_model(modelId=_haiku_model_id(), body=json.dumps(body))
    payload = json.loads(response["body"].read())
    text_blocks = [
        b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text"
    ]
    raw = "".join(text_blocks).strip()
    return {"raw": raw, "parsed": _coerce_json(raw)}


def _coerce_json(raw: str) -> dict:
    """Strip a code fence if the model returned one, then ``json.loads``."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # ```json\n ... \n```
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# Result normalisation
# ---------------------------------------------------------------------------


_VALID_INTENTS = {i.value: i for i in ReplyIntent}


def _normalise(parsed: dict) -> tuple[ReplyIntent, float, Optional[date], Optional[str]]:
    raw_intent = str(parsed.get("intent", "unknown")).strip().lower()
    intent = _VALID_INTENTS.get(raw_intent, ReplyIntent.UNKNOWN)
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    extracted_date: Optional[date] = None
    raw_date = parsed.get("date")
    if isinstance(raw_date, str) and raw_date.strip():
        try:
            extracted_date = date.fromisoformat(raw_date.strip())
        except ValueError:
            extracted_date = None

    raw_reason = parsed.get("reason")
    extracted_reason: Optional[str] = None
    if isinstance(raw_reason, str) and raw_reason.strip():
        extracted_reason = raw_reason.strip()[:500]

    return intent, confidence, extracted_date, extracted_reason


# ---------------------------------------------------------------------------
# Keyword fallback (multilingual)
# ---------------------------------------------------------------------------


# Phrase patterns — checked in priority order. First match wins.
# Confidence is set conservatively because these are heuristics.
_FALLBACK_PATTERNS: list[tuple[ReplyIntent, float, list[str]]] = [
    (
        ReplyIntent.STOP,
        0.85,
        [
            r"\bstop\b",
            r"\bunsubscribe\b",
            r"don'?t (?:call|contact|message)",
            r"मुझे (?:मत|न)\s*(?:बुलाओ|संपर्क)",
            r"नको\b",
        ],
    ),
    (
        ReplyIntent.OUT_OF_TOWN,
        0.80,
        [
            r"out of (?:town|station|city)",
            r"\b(?:travelling|traveling|on (?:vacation|holiday|trip))",
            r"not in (?:town|city|country)",
            r"बाहर\s+(?:गया|हूँ|हूं)",
            r"शहर\s+के\s+बाहर",
            r"ఊరి\s+బయట",
            r"travel\s+(?:ing|out)",
        ],
    ),
    (
        ReplyIntent.MEDICAL_DEFER,
        0.80,
        [
            r"\b(?:sick|ill|unwell|fever|covid|cold|flu)\b",
            r"\b(?:on|taking)\s+(?:antibiotics|medication|medicine|meds)\b",
            r"under (?:treatment|medication)",
            r"बीमार\s*हूँ?",
            r"ना?\s*तब?\s*ीयत",
            r"జ్వరం",
            r"తలనొప్పి",
        ],
    ),
    (
        ReplyIntent.RESCHEDULE_REQUEST,
        0.75,
        [
            r"can\s*i\s+come\s+(?:on\s+)?(?:next|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"\b(?:next|another)\s+(?:day|time|week)",
            r"reschedule",
            r"दूसरी\s*तारीख",
            r"मैं\s+(?:कल|परसों)\s+आ\s+सकता",
            r"మరో\s*తేదీ",
            r"\b(?:tomorrow|kal)\b",
        ],
    ),
    (
        ReplyIntent.UNRELATED_QUESTION,
        0.65,
        [
            r"\?$",                # ends with question mark
            r"^(?:what|where|when|why|how|which|who)\b",
            r"^(?:कौन|कहाँ|क्यों|कब|कैसे|क्या)\b",
        ],
    ),
]


def _keyword_fallback(text: str, language: str) -> ClassifiedReply:
    """Best-effort regex classifier. Last resort if Bedrock fails."""
    body = (text or "").lower().strip()

    # Run the rich-phrase patterns first
    for intent, conf, patterns in _FALLBACK_PATTERNS:
        for pat in patterns:
            if re.search(pat, body, flags=re.IGNORECASE | re.UNICODE):
                return ClassifiedReply(
                    intent=intent,
                    confidence=conf,
                    used_fallback=True,
                    model_used="keyword_fallback",
                    raw_response=f"matched: {pat}",
                )

    # Lean on the legacy YES/NO parser for the leftover bulk
    legacy = _legacy_intent.classify(body)
    if legacy == _legacy_intent.Intent.ACCEPT:
        return ClassifiedReply(
            intent=ReplyIntent.ACCEPT,
            confidence=0.80,
            used_fallback=True,
            model_used="keyword_fallback",
            raw_response="legacy_yes",
        )
    if legacy == _legacy_intent.Intent.DECLINE:
        return ClassifiedReply(
            intent=ReplyIntent.DECLINE,
            confidence=0.80,
            used_fallback=True,
            model_used="keyword_fallback",
            raw_response="legacy_no",
        )
    return ClassifiedReply(
        intent=ReplyIntent.UNKNOWN,
        confidence=0.0,
        used_fallback=True,
        model_used="keyword_fallback",
        raw_response="no_match",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _bedrock_available() -> bool:
    """We need at least the region + an AWS auth path."""
    if os.environ.get("BRIDGE_OS_DISABLE_BEDROCK") == "1":
        return False
    if not os.environ.get("BEDROCK_REGION") and not os.environ.get("AWS_REGION"):
        return False
    if not (
        os.environ.get("AWS_ACCESS_KEY_ID")
        or os.environ.get("AWS_PROFILE")
        or os.environ.get("AWS_DEFAULT_PROFILE")
    ):
        return False
    return True


def classify_reply(
    text: str, *, language: str = "en", context: dict | None = None
) -> ClassifiedReply:
    """Pure entry point — call from the webhook (or anywhere).

    Behaviour:
      1. If Bedrock isn't configured → keyword fallback.
      2. Call Haiku 4.5 with the strict-JSON system prompt.
      3. Parse + normalise → ClassifiedReply.
      4. If Bedrock returns confidence below the threshold OR ``unknown``,
         drop to keyword fallback so we never lose a clear YES/NO.
      5. Any exception inside Bedrock → fall back, no raise.
    """
    if not text or not text.strip():
        return ClassifiedReply(
            intent=ReplyIntent.UNKNOWN, confidence=0.0,
            used_fallback=True, model_used="keyword_fallback",
            raw_response="empty",
        )

    if not _bedrock_available():
        return _keyword_fallback(text, language)

    try:
        result = _call_bedrock(text, language, context)
    except Exception:
        logger.exception("Bedrock classify_reply failed — using fallback")
        fb = _keyword_fallback(text, language)
        fb.used_fallback = True
        return fb

    raw = result["raw"]
    try:
        parsed = result["parsed"]
    except Exception:
        logger.warning("Bedrock returned non-JSON: %r — using fallback", raw[:120])
        fb = _keyword_fallback(text, language)
        fb.used_fallback = True
        fb.raw_response = raw
        return fb

    intent, confidence, extracted_date, extracted_reason = _normalise(parsed)
    out = ClassifiedReply(
        intent=intent,
        confidence=confidence,
        extracted_date=extracted_date,
        extracted_reason=extracted_reason,
        model_used=_haiku_model_id(),
        raw_response=raw,
        used_fallback=False,
    )

    # If the Bedrock result is too uncertain, defer to keyword fallback so
    # an obvious YES doesn't get treated as UNKNOWN.
    if intent == ReplyIntent.UNKNOWN or confidence < CONFIDENCE_THRESHOLD:
        fb = _keyword_fallback(text, language)
        if fb.intent != ReplyIntent.UNKNOWN:
            # Keep the original model audit, but use the fallback's intent.
            fb.used_fallback = True
            fb.raw_response = raw
            fb.model_used = f"{_haiku_model_id()}+keyword_fallback"
            return fb
    return out
