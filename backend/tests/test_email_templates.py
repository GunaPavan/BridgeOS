"""Phase E2 — email template rendering tests."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.email_templates import (
    ALL_TEMPLATE_KEYS,
    render_caregiver_daily_digest,
    render_caregiver_emergency_alert,
    render_coordinator_failure_alert,
)


def test_all_templates_registered() -> None:
    assert set(ALL_TEMPLATE_KEYS) == {
        "caregiver_daily_digest",
        "caregiver_emergency_alert",
        "coordinator_failure_alert",
    }


def test_daily_digest_renders_full() -> None:
    r = render_caregiver_daily_digest(
        caregiver_first="Anjali",
        patient_name="Riya",
        next_transfusion_date=date(2026, 6, 21),
        days_until=14,
        active_donor_count=6,
        bridge_health_label="stable",
        pending_donor_count=2,
    )
    assert r.template_key == "caregiver_daily_digest"
    assert "Anjali" in r.body
    assert "Riya" in r.body
    assert "2026-06-21" in r.body
    assert "14 days" in r.body
    assert "6" in r.body
    assert "stable" in r.body


def test_daily_digest_handles_overdue() -> None:
    r = render_caregiver_daily_digest(
        caregiver_first="A",
        patient_name="X",
        next_transfusion_date=date(2026, 6, 1),
        days_until=-3,
        active_donor_count=3,
        bridge_health_label="critical",
    )
    assert "overdue" in r.body.lower()


def test_daily_digest_handles_missing_caregiver_first() -> None:
    r = render_caregiver_daily_digest(
        caregiver_first="",
        patient_name="X",
        next_transfusion_date=None,
        days_until=None,
        active_donor_count=0,
        bridge_health_label="critical",
    )
    assert "Hi there" in r.body


def test_emergency_alert_renders() -> None:
    r = render_caregiver_emergency_alert(
        caregiver_first="Anjali",
        patient_name="Riya",
        slot_date=date(2026, 6, 9),
        hospital="Apollo Hospitals",
        tier_label="Tier 3",
    )
    assert "URGENT" in r.subject
    assert "Riya" in r.subject
    assert "2026-06-09" in r.body
    assert "Apollo Hospitals" in r.body
    assert "Tier 3" in r.body


def test_coordinator_failure_alert_renders() -> None:
    r = render_coordinator_failure_alert(
        patient_name="Riya",
        slot_date=date(2026, 6, 9),
        tier_label="Tier 3",
        wave_id="abcd1234",
        pings_sent=12,
        pings_accepted=0,
        pings_declined=4,
        pings_no_reply=8,
    )
    assert "Tier 3" in r.subject
    assert "abcd1234" in r.body
    assert "sent     : 12" in r.body
    assert "accepted : 0" in r.body
