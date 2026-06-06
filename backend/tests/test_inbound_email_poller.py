"""E8 — InboundEmailPoller worker tests.

The poller is a thin orchestration layer around the SES inbound parser +
the inbound_email_handler. We test:

  - In mock mode, it no-ops cleanly (no S3 to read)
  - When list_pending_inbound_emails / fetch_and_parse are monkeypatched,
    the handler is invoked and stats update
  - Failures are isolated (one bad email doesn't crash the loop)
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.integrations import sns_client
from app.integrations.ses_inbound import ParsedInboundEmail
from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    CaregiverRelation,
    ContactChannel,
    Patient,
)
from app.outreach.inbound_email_poller import InboundEmailPoller


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch):
    monkeypatch.setenv("BRIDGE_OS_DISABLE_AWS", "1")
    sns_client._reset_mock_topics_for_tests()


def test_poller_no_ops_in_mock_mode():
    """Without AWS creds, the poller drains nothing — and doesn't blow up."""
    poller = InboundEmailPoller(session_factory=SessionLocal, poll_interval_seconds=0.1)
    n = poller._drain_once()
    assert n == 0
    assert poller.stats.polls == 1
    assert poller.stats.processed == 0


def test_poller_processes_one_email_when_keys_found(db_session: Session):
    """Stub S3 to return one key + a parsed payload; poller should invoke
    the handler and bump stats."""
    # Create a caregiver patient matching the email
    patient = Patient(
        name="Riya", age=8, blood_group=BloodGroup.B_POS,
        rh_negative=False, kell_negative=False,
        city="Hyderabad", state="Telangana", lat=17.39, lng=78.46,
        hospital="Apollo", transfusion_cadence_days=21,
        last_transfusion_date=date(2026, 5, 1), active=True,
        caregiver_name="Anita", caregiver_phone="+919900000077",
        caregiver_email="anita-poll@example.com",
        caregiver_relation=CaregiverRelation.MOTHER,
        caregiver_preferred_channel=ContactChannel.EMAIL,
    )
    db_session.add(patient)
    db_session.flush()
    db_session.add(Bridge(patient_id=patient.id, name="b", status=BridgeStatus.ACTIVE))
    db_session.commit()

    fake_email = ParsedInboundEmail(
        from_email="anita-poll@example.com",
        to_email="ops@bridge-os.click",
        subject="Re: digest",
        body_text="STOP - we are sorted",
        body_html=None,
        message_id="poller-test-001",
        received_at=datetime.utcnow(),
    )

    with patch(
        "app.outreach.inbound_email_poller.aws_available", return_value=True
    ), patch(
        "app.outreach.inbound_email_poller.list_pending_inbound_emails",
        return_value=["inbox/poller-test-001.eml"],
    ), patch(
        "app.outreach.inbound_email_poller.fetch_and_parse",
        return_value=fake_email,
    ), patch(
        "app.outreach.inbound_email_poller.mark_processed",
        return_value=True,
    ):
        poller = InboundEmailPoller(
            session_factory=SessionLocal, poll_interval_seconds=0.1
        )
        n = poller._drain_once()
        assert n == 1
        assert poller.stats.fetched == 1
        assert poller.stats.processed == 1
        assert poller.stats.failed == 0


def test_poller_handles_parse_failure_gracefully():
    """If fetch_and_parse returns None, stats.failed increments but the
    loop doesn't crash."""
    with patch(
        "app.outreach.inbound_email_poller.aws_available", return_value=True
    ), patch(
        "app.outreach.inbound_email_poller.list_pending_inbound_emails",
        return_value=["inbox/bad.eml"],
    ), patch(
        "app.outreach.inbound_email_poller.fetch_and_parse",
        return_value=None,
    ):
        poller = InboundEmailPoller(
            session_factory=SessionLocal, poll_interval_seconds=0.1
        )
        n = poller._drain_once()
        assert n == 0
        assert poller.stats.failed == 1


def test_poller_lifecycle_start_stop_idempotent():
    """start() should be safe to call twice; stop() should be safe even if
    not started."""
    poller = InboundEmailPoller(
        session_factory=SessionLocal, poll_interval_seconds=10.0
    )
    poller.start()
    poller.start()  # idempotent
    assert poller._thread is not None
    assert poller._thread.is_alive()
    poller.stop()
    assert poller._thread is None
    poller.stop()  # safe to call again
