"""Tests for the Care Agent's script-based language detection."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.agent.language import detect_language


# ----- detect_language unit tests -----


def test_pure_english_returns_fallback() -> None:
    assert detect_language("Hello, how are you?", fallback="en") == "en"
    assert detect_language("How are you?", fallback="hi") == "hi"


def test_empty_returns_fallback() -> None:
    assert detect_language("", fallback="en") == "en"
    assert detect_language("", fallback="te") == "te"


def test_hindi_devanagari_detected() -> None:
    # नमस्ते = "namaste"
    assert detect_language("नमस्ते, क्या हाल है?", fallback="en") == "hi"


def test_telugu_detected() -> None:
    # తెలుగు = "Telugu"
    assert detect_language("నమస్కారం, మీరు ఎలా ఉన్నారు?", fallback="en") == "te"


def test_tamil_detected() -> None:
    assert detect_language("வணக்கம், எப்படி இருக்கிறீர்கள்?", fallback="en") == "ta"


def test_bengali_detected() -> None:
    assert detect_language("নমস্কার, কেমন আছেন?", fallback="en") == "bn"


def test_kannada_detected() -> None:
    assert detect_language("ನಮಸ್ಕಾರ, ಹೇಗಿದ್ದೀರಿ?", fallback="en") == "kn"


def test_gujarati_detected() -> None:
    assert detect_language("નમસ્તે, કેમ છો?", fallback="en") == "gu"


def test_mixed_script_picks_majority() -> None:
    # 8 chars Telugu + 4 chars Latin → te
    assert detect_language("Hello నమస్కారం", fallback="en") == "te"


def test_punctuation_and_numbers_dont_confuse() -> None:
    assert detect_language("नमस्ते 123!?", fallback="en") == "hi"


# ----- end-to-end API behaviour -----


def test_chat_auto_detects_hindi_from_devanagari(client: TestClient) -> None:
    body = client.post(
        "/agent/chat",
        json={"query": "नमस्ते, अरव कैसा है?", "language": "en"},
    ).json()
    assert body["language"] == "hi"
    assert body["detected_language"] == "hi"
    assert body["user_message"]["language"] == "hi"
    assert body["assistant_message"]["language"] == "hi"


def test_chat_auto_detects_telugu_overriding_explicit_english(
    client: TestClient,
) -> None:
    body = client.post(
        "/agent/chat",
        json={"query": "నమస్కారం, మీరు ఏమి చేయగలరు?", "language": "en"},
    ).json()
    assert body["language"] == "te"
    assert body["detected_language"] == "te"


def test_chat_keeps_explicit_language_when_query_is_latin(
    client: TestClient,
) -> None:
    body = client.post(
        "/agent/chat",
        json={"query": "Hello, what can you do?", "language": "hi"},
    ).json()
    # Detection found no Indic, fallback (hi) is kept; no override flag.
    assert body["language"] == "hi"
    assert body["detected_language"] is None


def test_chat_no_detected_language_when_detection_matches_request(
    client: TestClient,
) -> None:
    body = client.post(
        "/agent/chat",
        json={"query": "नमस्ते", "language": "hi"},
    ).json()
    assert body["language"] == "hi"
    # Detection equals request — no override flagged.
    assert body["detected_language"] is None
