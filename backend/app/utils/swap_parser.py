"""G6 — parse donor inbound swap requests.

Donors text things like:
    "swap with priya on aug 15"
    "swap aug 15 priya"
    "swap 2026-08-15 priya sharma"
    "swap with priya tomorrow"

We extract:
    - target name fragment (lowercased, whitespace-collapsed)
    - target date (date object)

Out-of-scope for the hackathon: full natural language parsing. We support
enough formats to cover the demo + a reasonable subset of real coordinator
usage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional


# ----- date parsing -----

_ISO_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_DMY_RE = re.compile(r"\b(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?\b")
_MONTH_NAMES = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_MONTH_DAY_RE = re.compile(
    r"\b(?P<month>jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+(?P<day>\d{1,2})(?:\s+(?P<year>\d{4}))?\b",
    flags=re.IGNORECASE,
)
_DAY_MONTH_RE = re.compile(
    r"\b(?P<day>\d{1,2})\s+(?P<month>jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)(?:\s+(?P<year>\d{4}))?\b",
    flags=re.IGNORECASE,
)


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date(text: str, today: Optional[date] = None) -> Optional[date]:
    """Pull a date out of free-form text. Returns None if nothing parses."""
    today = today or date.today()
    lower = text.lower()

    # Relative
    if re.search(r"\btoday\b", lower):
        return today
    if re.search(r"\btomorrow\b", lower):
        return today + timedelta(days=1)
    if re.search(r"\bnext\s+week\b", lower):
        return today + timedelta(days=7)

    # ISO YYYY-MM-DD
    m = _ISO_RE.search(text)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # DD/MM or DD/MM/YYYY (Indian/UK convention)
    m = _DMY_RE.search(text)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year_raw = m.group(3)
        if year_raw:
            year = int(year_raw)
            if year < 100:
                year += 2000
        else:
            year = today.year
        d = _safe_date(year, month, day)
        if d is not None and d < today:
            # If unqualified date is in the past this year, assume next year
            d = _safe_date(year + 1, month, day) if year_raw is None else d
        if d is not None:
            return d

    # "aug 15" / "August 15 2026"
    m = _MONTH_DAY_RE.search(lower)
    if m:
        month = _MONTH_NAMES[m.group("month").lower()]
        day = int(m.group("day"))
        year = int(m.group("year")) if m.group("year") else today.year
        d = _safe_date(year, month, day)
        if d is not None and d < today and not m.group("year"):
            d = _safe_date(year + 1, month, day)
        if d is not None:
            return d

    # "15 aug"
    m = _DAY_MONTH_RE.search(lower)
    if m:
        month = _MONTH_NAMES[m.group("month").lower()]
        day = int(m.group("day"))
        year = int(m.group("year")) if m.group("year") else today.year
        d = _safe_date(year, month, day)
        if d is not None and d < today and not m.group("year"):
            d = _safe_date(year + 1, month, day)
        if d is not None:
            return d

    return None


# ----- swap intent -----


@dataclass(frozen=True)
class ParsedSwap:
    name_fragment: str
    date: date


_SWAP_KEYWORD_RE = re.compile(r"\bswap\b", flags=re.IGNORECASE)
# Stop words we ignore when extracting the name fragment
_STOPWORDS = {
    "swap", "with", "for", "on", "to", "and", "please", "pls", "the", "my",
    "slot", "donate", "donating", "today", "tomorrow", "next", "week",
}


def _extract_name_fragment(text: str, parsed_date: Optional[date]) -> str:
    """Remove the keyword + date tokens + stopwords; whatever remains is the name."""
    cleaned = text.lower()

    # Strip ISO date
    cleaned = _ISO_RE.sub(" ", cleaned)
    cleaned = _DMY_RE.sub(" ", cleaned)
    cleaned = _MONTH_DAY_RE.sub(" ", cleaned)
    cleaned = _DAY_MONTH_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\b(today|tomorrow|next\s+week)\b", " ", cleaned, flags=re.IGNORECASE)

    # Tokenise + drop stopwords
    tokens = [t for t in re.split(r"\s+", cleaned.strip()) if t]
    tokens = [t for t in tokens if t not in _STOPWORDS]

    return " ".join(tokens).strip()


def parse_swap(text: str, today: Optional[date] = None) -> Optional[ParsedSwap]:
    """Return ParsedSwap when the inbound looks like a swap request, else None.

    A swap inbound must contain the word "swap" AND a parseable date.
    """
    if not _SWAP_KEYWORD_RE.search(text or ""):
        return None
    d = parse_date(text, today=today)
    if d is None:
        return None
    name = _extract_name_fragment(text, d)
    if not name:
        return None
    return ParsedSwap(name_fragment=name, date=d)
