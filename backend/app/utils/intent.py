"""Inbound WhatsApp intent parsing.

Donor replies to a recruit_invite (or slot_reminder, swap_request) with
short tokens. We need to classify them as ACCEPT / DECLINE / OTHER across
the eight languages Bridge OS supports.

Heuristic — no NLP needed:
    1. Lowercase, strip punctuation, take the FIRST WORD only.
    2. Look up in a per-language ACCEPT / DECLINE set.
    3. Fall back to OTHER.

The donor's preferred_language is used as a hint, but every language's
tokens are always tried so we don't penalise a Telugu donor who replies "YES".
"""

from __future__ import annotations

from enum import Enum


class Intent(str, Enum):
    ACCEPT = "accept"
    DECLINE = "decline"
    OTHER = "other"


# Tokens that count as ACCEPT. Lowercased; first-word match.
_ACCEPT_TOKENS = {
    # English
    "yes", "y", "yeah", "yep", "yup", "ok", "okay", "sure", "join", "confirm", "accept", "agreed",
    # Hindi (Devanagari + transliteration)
    "हाँ", "हां", "जी", "ठीक", "सही", "स्वीकार",
    "haan", "haa", "han", "ji", "thik", "theek", "sahi", "haanji",
    # Telugu
    "అవును", "సరే", "ఒప్పుకుంటున్నాను",
    "avunu", "sare", "okay", "oppukuntunnanu",
    # Tamil
    "ஆம்", "சரி", "ஒத்துக்கொள்கிறேன்",
    "aam", "ama", "sari", "seri", "othukolgiren",
    # Marathi
    "होय", "होकार", "बरोबर",
    "hoy", "hokar", "barobar",
    # Bengali
    "হ্যাঁ", "হাঁ", "ঠিক",
    "haa", "hyan", "thik",
    # Kannada
    "ಹೌದು", "ಸರಿ",
    "houdu", "haudu", "sari",
    # Gujarati
    "હા", "બરાબર", "સ્વીકાર",
    "ha", "haa", "barabar", "svikar",
}


# Tokens that count as DECLINE.
_DECLINE_TOKENS = {
    # English
    "no", "n", "nope", "stop", "decline", "reject", "cancel", "leave", "skip",
    # Hindi
    "नहीं", "मत", "ना",
    "nahi", "nahin", "na", "mat",
    # Telugu
    "కాదు", "వద్దు", "లేదు",
    "kadu", "vaddu", "ledu",
    # Tamil
    "இல்லை", "வேண்டாம்",
    "illai", "illa", "vendam", "venaam",
    # Marathi
    "नाही", "नको",
    "nahi", "nako",
    # Bengali
    "না", "নয়",
    "naa", "noy",
    # Kannada
    "ಇಲ್ಲ", "ಬೇಡ",
    "illa", "beda",
    # Gujarati
    "ના", "નહીં",
    "naa", "nahin",
}


# ASCII punctuation we'll strip from token edges. We deliberately don't
# use Python's regex `\W` because in Indic scripts the combining marks
# (vowel signs, anusvara) are classified as non-word, which would split
# "हाँ" into just "ह" and drop the rest.
_PUNCT_STRIP = ".,!?;:'\"()[]{}<>«»‘’“”¿¡*~`/\\|"


def _first_word(text: str) -> str:
    """Lowercase + strip surrounding punctuation; return the first whitespace-separated token."""
    if not text:
        return ""
    parts = text.strip().split()
    if not parts:
        return ""
    return parts[0].strip(_PUNCT_STRIP).lower()


def classify(text: str) -> Intent:
    """Classify an inbound WhatsApp body into ACCEPT / DECLINE / OTHER."""
    token = _first_word(text)
    if not token:
        return Intent.OTHER
    if token in _ACCEPT_TOKENS:
        return Intent.ACCEPT
    if token in _DECLINE_TOKENS:
        return Intent.DECLINE
    return Intent.OTHER
