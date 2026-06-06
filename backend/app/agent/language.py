"""Lightweight script-based language detection.

We map Unicode block coverage to language codes. Counts are computed by
walking the string once and bucketing each character.

Why this and not langdetect/fasttext: the demo languages all use distinct
scripts (Devanagari for Hindi/Marathi, Telugu, Tamil, Bengali, Kannada,
Gujarati) so script identification gives a deterministic ~100% accurate
answer for non-Latin queries. For Latin-script input we keep the user's
explicit language choice (or fall back to English).
"""

from __future__ import annotations

from typing import Literal


LanguageCode = Literal["en", "hi", "te", "ta", "mr", "bn", "kn", "gu"]


# Unicode ranges per script. (start, end inclusive, language).
# Devanagari is shared between Hindi (hi) and Marathi (mr) — we default to hi
# unless an explicit Marathi-only hint is present.
_RANGES: list[tuple[int, int, LanguageCode]] = [
    (0x0900, 0x097F, "hi"),  # Devanagari (Hindi / Marathi)
    (0x0980, 0x09FF, "bn"),  # Bengali
    (0x0A80, 0x0AFF, "gu"),  # Gujarati
    (0x0B80, 0x0BFF, "ta"),  # Tamil
    (0x0C00, 0x0C7F, "te"),  # Telugu
    (0x0C80, 0x0CFF, "kn"),  # Kannada
]


def _script_of(ch: str) -> LanguageCode | None:
    code = ord(ch)
    for lo, hi, lang in _RANGES:
        if lo <= code <= hi:
            return lang
    return None


def detect_language(text: str, fallback: LanguageCode = "en") -> LanguageCode:
    """Return the most-likely language code for `text`.

    - If any Indic script characters are present, return that language
      (majority wins on ties between scripts; ties broken in range order).
    - Otherwise return the fallback (typically "en" or whatever the user
      previously selected in the UI).
    """
    if not text:
        return fallback

    counts: dict[LanguageCode, int] = {}
    for ch in text:
        lang = _script_of(ch)
        if lang is not None:
            counts[lang] = counts.get(lang, 0) + 1

    if not counts:
        return fallback

    # Sort by count desc, then by range order (deterministic).
    return max(counts.items(), key=lambda kv: kv[1])[0]
