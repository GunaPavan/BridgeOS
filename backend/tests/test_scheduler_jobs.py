"""Test the pure job handlers in app/scheduler/jobs.py.

Phase A handlers exercised:
  - auto_run_cycle          (calls run_cycle, returns counts in payload)
  - auto_expire_and_escalate (no-op on a clean DB → 0 expired)

Phase B handlers asserted to return SKIPPED until they're wired in next.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.scheduler.jobs import (
    auto_expire_and_escalate,
    auto_pending_nudge,
    auto_post_donation_thank_you,
    auto_pre_donation_reminder,
    auto_run_cycle,
)


def test_auto_run_cycle_returns_summary_payload(db_session: Session) -> None:
    """On an empty DB the allocator finds zero open slots and returns a
    well-formed summary."""
    now = datetime(2026, 6, 7, 10, 0, 0)
    result = auto_run_cycle(db=db_session, now=now)
    assert result.skipped_reason is None
    assert result.items_processed == 0
    p = result.payload
    for key in (
        "open_slots",
        "waves_created",
        "pings_planned",
        "critical_slots",
        "high_slots",
        "medium_slots",
        "fully_covered_slots",
        "shortfall_slots",
    ):
        assert key in p


def test_auto_expire_and_escalate_no_op_on_empty(db_session: Session) -> None:
    now = datetime(2026, 6, 7, 10, 0, 0)
    result = auto_expire_and_escalate(db=db_session, now=now)
    assert result.skipped_reason is None
    assert result.items_processed == 0
    assert result.payload["expired_count"] == 0
    assert result.payload["escalated_count"] == 0


def test_phase_b_handlers_no_op_on_empty_db(db_session: Session, monkeypatch) -> None:
    """With Phase B wired, the follow-up handlers query the DB. On an empty
    DB they find no qualifying pings and return items_processed=0 with no
    skipped_reason."""
    # Force not-quiet so the jobs actually scan the DB
    monkeypatch.setattr("app.scheduler.jobs._is_quiet_hours_now", lambda now: False)
    now = datetime(2026, 6, 7, 10, 0, 0)
    for handler in (
        auto_pending_nudge,
        auto_pre_donation_reminder,
        auto_post_donation_thank_you,
    ):
        result = handler(db=db_session, now=now)
        assert result.skipped_reason is None
        assert result.items_processed == 0
        assert result.payload.get("candidates") == 0
