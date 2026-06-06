"""Dataset-anchored "today" reference.

The Blood Warriors dataset is a SNAPSHOT — its most recent records are dated
August / December 2025. Computing time-deltas against the real wall-clock
makes everything look catastrophically overdue (a transfusion scheduled for
2025-09-15 is 250+ days "overdue" when wall-clock is 2026-06-06).

Production-grade fix: anchor every "today" calculation to the dataset's own
reference date — derived from the most recent timestamp in the loaded data.
That's how every analytics platform handles snapshot data.

Behaviour:
- If the DB has any data with a recent `last_contacted_date`, `registration_date`,
  or `last_donation_date`, the most recent such date becomes the system clock.
- Otherwise (empty DB), fall back to wall-clock today.
- Cached for 5 minutes; invalidated on ingest.

Public surface:
    today() -> date              # the system's "now" for snapshot reasoning
    reference_label() -> str     # human-readable explanation of the anchor
    invalidate_cache()
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from threading import Lock

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Donor

_CACHE_TTL_SECONDS = 300
_cache: tuple[date, datetime] | None = None
_cache_lock = Lock()


def invalidate_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def _query_reference_date(db: Session) -> date | None:
    """Pick the most recent donor timestamp as the dataset's 'today'.

    Defensive against:
        - Future-dated data noise (e.g. last_donation_date = 2029-09-30 in
          a 2025 dataset) — capped to wall-clock today.
        - Ingest-time defaults: ``registered_at`` is filled with
          ``datetime.utcnow()`` for any donor without a parseable
          registration date, so it's NOT a reliable anchor and we don't use it.

    Only ``last_contacted_date`` and ``last_donation_date`` reflect actual
    data timestamps. We pick the max of those two and add a 7-day forward
    buffer so events recorded just after the snapshot don't appear as
    "in the future".
    """
    wall_today = date.today()
    candidates: list[date] = []
    for col in (Donor.last_contacted_date, Donor.last_donation_date):
        v = db.execute(select(func.max(col)).where(col <= wall_today)).scalar()
        if v is not None:
            if isinstance(v, datetime):
                v = v.date()
            candidates.append(v)
    if not candidates:
        return None
    anchor = max(candidates) + timedelta(days=7)
    # If the data extends to (near) wall-clock today, don't anchor — just use
    # wall-clock. The anchor only kicks in for genuinely stale snapshot data
    # (>30 days old). This keeps unit tests with date.today() relative
    # fixtures working naturally.
    if (wall_today - anchor).days < 30:
        return None
    return anchor


def today(db: Session | None = None) -> date:
    """Return the dataset-anchored 'today'. Falls back to wall-clock if empty."""
    global _cache
    now = datetime.now(timezone.utc)
    with _cache_lock:
        if _cache is not None and (now - _cache[1]).total_seconds() < _CACHE_TTL_SECONDS:
            return _cache[0]

    owned_session = db is None
    if db is None:
        db = SessionLocal()
    try:
        ref = _query_reference_date(db)
    finally:
        if owned_session:
            db.close()

    anchor = ref if ref is not None else date.today()
    with _cache_lock:
        _cache = (anchor, now)
    return anchor


def reference_label(db: Session | None = None) -> str:
    """One-line explanation of which date the system is anchored to."""
    t = today(db)
    real = date.today()
    if t >= real:
        return f"System clock: {t.isoformat()} (live)"
    delta_days = (real - t).days
    return (
        f"System clock anchored to dataset reference {t.isoformat()} "
        f"(wall-clock is {delta_days} day{'s' if delta_days != 1 else ''} ahead)"
    )


def system_clock_info(db: Session | None = None) -> dict:
    """JSON payload for /system/clock endpoint."""
    t = today(db)
    real = date.today()
    return {
        "today": t.isoformat(),
        "wall_clock": real.isoformat(),
        "is_anchored": t < real,
        "days_anchored_back": (real - t).days,
        "label": reference_label(db),
    }
