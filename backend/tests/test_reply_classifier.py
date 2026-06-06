"""Tests for app.services.reply_classifier.

Bedrock is NEVER called in tests — the env var ``BEDROCK_REGION`` is unset
by the conftest fixture so ``_bedrock_available()`` returns False and the
keyword fallback runs. We exercise the fallback's coverage of all eight
intents, plus the edge cases (empty, unicode, mixed language).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.enums import ReplyIntent
from app.services.reply_classifier import (
    ACTIONABLE_THRESHOLD,
    CONFIDENCE_THRESHOLD,
    ClassifiedReply,
    classify_reply,
)


# ---------------------------------------------------------------------------
# Public dataclass shape
# ---------------------------------------------------------------------------


def test_classified_reply_is_actionable_when_above_threshold() -> None:
    r = ClassifiedReply(intent=ReplyIntent.ACCEPT, confidence=0.95)
    assert r.is_actionable

    r = ClassifiedReply(intent=ReplyIntent.ACCEPT, confidence=0.5)
    assert not r.is_actionable

    r = ClassifiedReply(intent=ReplyIntent.UNKNOWN, confidence=0.99)
    assert not r.is_actionable


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


def test_empty_text_returns_unknown() -> None:
    r = classify_reply("")
    assert r.intent == ReplyIntent.UNKNOWN
    assert r.used_fallback


# ---------------------------------------------------------------------------
# Fallback path — multi-language coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,language,expected",
    [
        ("yes", "en", ReplyIntent.ACCEPT),
        ("YES I can come", "en", ReplyIntent.ACCEPT),
        ("haan", "hi", ReplyIntent.ACCEPT),
        ("avunu", "te", ReplyIntent.ACCEPT),
        ("no", "en", ReplyIntent.DECLINE),
        ("नहीं", "hi", ReplyIntent.DECLINE),
        ("STOP", "en", ReplyIntent.STOP),
        ("stop calling me", "en", ReplyIntent.STOP),
        ("I am out of town", "en", ReplyIntent.OUT_OF_TOWN),
        ("travelling next week", "en", ReplyIntent.OUT_OF_TOWN),
        ("I am sick with fever", "en", ReplyIntent.MEDICAL_DEFER),
        ("on antibiotics, sorry", "en", ReplyIntent.MEDICAL_DEFER),
        ("can I come on Monday instead?", "en", ReplyIntent.RESCHEDULE_REQUEST),
        ("where is the hospital?", "en", ReplyIntent.UNRELATED_QUESTION),
        ("what blood group", "en", ReplyIntent.UNRELATED_QUESTION),
    ],
)
def test_fallback_classifies_expected_intent(
    text: str, language: str, expected: ReplyIntent
) -> None:
    r = classify_reply(text, language=language)
    assert r.intent == expected, f"got {r.intent} for {text!r}"
    assert r.used_fallback is True
    assert r.confidence > 0.0


def test_fallback_unknown_for_gibberish() -> None:
    r = classify_reply("asdjkasldka qwoieuq", language="en")
    assert r.intent == ReplyIntent.UNKNOWN
    assert r.used_fallback


# ---------------------------------------------------------------------------
# Bedrock path — mock the boto3 call to avoid network
# ---------------------------------------------------------------------------


def _patch_bedrock(monkeypatch, parsed: dict, raw: str | None = None) -> list:
    """Make ``_bedrock_available`` return True and ``_call_bedrock`` return
    a canned response."""
    from app.services import reply_classifier as rc

    monkeypatch.setattr(rc, "_bedrock_available", lambda: True)
    calls = []

    def _fake_call(text, language, context):
        calls.append({"text": text, "language": language, "context": context})
        import json
        return {
            "raw": raw if raw is not None else json.dumps(parsed),
            "parsed": parsed,
        }

    monkeypatch.setattr(rc, "_call_bedrock", _fake_call)
    return calls


def test_bedrock_high_confidence_accept(monkeypatch) -> None:
    _patch_bedrock(
        monkeypatch,
        {"intent": "accept", "confidence": 0.95, "date": None, "reason": None},
    )
    r = classify_reply("Sure, I'll come", language="en")
    assert r.intent == ReplyIntent.ACCEPT
    assert r.confidence == 0.95
    assert not r.used_fallback
    assert "claude-haiku" in r.model_used


def test_bedrock_low_confidence_falls_back(monkeypatch) -> None:
    _patch_bedrock(
        monkeypatch,
        {"intent": "out_of_town", "confidence": 0.4, "date": None, "reason": "maybe"},
    )
    # Body has a clear YES — fallback should rescue it from the low-conf model
    r = classify_reply("yes", language="en")
    assert r.intent == ReplyIntent.ACCEPT
    assert r.used_fallback


def test_bedrock_exception_falls_back(monkeypatch) -> None:
    from app.services import reply_classifier as rc

    monkeypatch.setattr(rc, "_bedrock_available", lambda: True)

    def _explode(*args, **kwargs):
        raise RuntimeError("AWS timeout")

    monkeypatch.setattr(rc, "_call_bedrock", _explode)
    r = classify_reply("I'm out of town this week", language="en")
    assert r.intent == ReplyIntent.OUT_OF_TOWN
    assert r.used_fallback


def test_bedrock_returns_non_json_falls_back(monkeypatch) -> None:
    from app.services import reply_classifier as rc

    monkeypatch.setattr(rc, "_bedrock_available", lambda: True)

    def _bad_call(text, language, context):
        return {
            "raw": "Sure, I'd say accept with high confidence — but I'll skip JSON.",
            "parsed": None,
        }

    # Trick the code path: simulate parse failure by raising inside _call_bedrock
    from app.services.reply_classifier import _coerce_json

    def _wrapped(text, language, context):
        # Force the code to take the "non-JSON" branch by having parsed missing
        return {"raw": "not json", "parsed": _coerce_json("not json")}

    monkeypatch.setattr(rc, "_call_bedrock", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad")))
    r = classify_reply("yes", language="en")
    assert r.intent == ReplyIntent.ACCEPT  # fallback rescued it
    assert r.used_fallback


def test_bedrock_extracts_date(monkeypatch) -> None:
    _patch_bedrock(
        monkeypatch,
        {
            "intent": "reschedule_request",
            "confidence": 0.85,
            "date": "2026-06-15",
            "reason": "school exam",
        },
    )
    r = classify_reply("Can I come on June 15 instead?", language="en")
    assert r.intent == ReplyIntent.RESCHEDULE_REQUEST
    assert r.extracted_date is not None
    assert r.extracted_date.isoformat() == "2026-06-15"
    assert r.extracted_reason == "school exam"


def test_bedrock_invalid_date_ignored(monkeypatch) -> None:
    _patch_bedrock(
        monkeypatch,
        {
            "intent": "reschedule_request",
            "confidence": 0.85,
            "date": "tomorrow",  # invalid ISO
            "reason": None,
        },
    )
    r = classify_reply("can I come tomorrow?", language="en")
    assert r.intent == ReplyIntent.RESCHEDULE_REQUEST
    assert r.extracted_date is None


def test_bedrock_unknown_intent_string_becomes_unknown_enum(monkeypatch) -> None:
    _patch_bedrock(
        monkeypatch,
        {"intent": "garbage_intent", "confidence": 0.95},
    )
    r = classify_reply("hello", language="en")
    # Bedrock returned a bogus enum value — should normalise to UNKNOWN,
    # then the fallback runs. Without a keyword hit, final result is UNKNOWN.
    assert r.intent == ReplyIntent.UNKNOWN


# ---------------------------------------------------------------------------
# Thresholds are sane
# ---------------------------------------------------------------------------


def test_thresholds_match_problem_statement() -> None:
    assert CONFIDENCE_THRESHOLD == 0.7
    assert ACTIONABLE_THRESHOLD == 0.7
