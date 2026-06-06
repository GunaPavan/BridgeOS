"""S3 poller worker — drains real inbound emails written by SES receipt rule.

Pipeline (live mode):

    Sender's MUA          → bridge-os.click (MX → SES)
                          → SES receipt rule
                          → S3 PutObject team019-bridge-os-inbound-emails/inbox/<msg>
                          → THIS WORKER (poll every 5s, parse, classify, fan out)

Pipeline (mock mode / no AWS):

    Worker no-ops — nothing in S3 to drain. The /emails/inbound-webhook API
    exercises the same downstream code path via JSON payloads.

This worker is the production analogue of the WhatsApp DispatchWorker (SQS)
and EventDispatcher (SNS). All three share the same loop shape: poll, drain,
process, mark-done.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.integrations.aws import aws_available
from app.integrations.ses_inbound import (
    fetch_and_parse,
    list_pending_inbound_emails,
    mark_processed,
)

logger = logging.getLogger(__name__)


@dataclass
class InboundEmailPollerStats:
    polls: int = 0
    fetched: int = 0
    processed: int = 0
    failed: int = 0
    last_poll_at: Optional[datetime] = None
    started_at: Optional[datetime] = None


class InboundEmailPoller:
    """Long-running thread that pulls inbound emails out of S3.

    Same shape as DispatchWorker (SQS) — start() + stop() + stats.
    Started by SchedulerRuntime in live mode; quietly no-ops otherwise.
    """

    def __init__(self, *, session_factory, poll_interval_seconds: float = 5.0) -> None:
        self._SessionLocal = session_factory
        self._poll_interval = poll_interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.stats = InboundEmailPollerStats()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self.stats.started_at = datetime.utcnow()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="InboundEmailPoller"
        )
        self._thread.start()
        logger.info("InboundEmailPoller started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("InboundEmailPoller stopped")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._drain_once()
            except Exception:  # pragma: no cover
                logger.exception("InboundEmailPoller drain raised")
            self._stop.wait(self._poll_interval)

    def _drain_once(self) -> int:
        """One poll cycle. Returns count of emails processed."""
        self.stats.polls += 1
        self.stats.last_poll_at = datetime.utcnow()

        if not aws_available():
            return 0  # no S3 to poll in mock mode

        keys = list_pending_inbound_emails(max_keys=20)
        if not keys:
            return 0

        # Import inside the loop so the prod handler picks up any code reloads
        from app.services.inbound_email_handler import process_inbound_email

        processed = 0
        for key in keys:
            parsed = fetch_and_parse(key)
            if parsed is None:
                self.stats.failed += 1
                continue
            self.stats.fetched += 1
            try:
                with self._SessionLocal() as db:
                    process_inbound_email(db, email_obj=parsed)
                mark_processed(key)
                self.stats.processed += 1
                processed += 1
            except Exception:  # pragma: no cover
                logger.exception("Failed to process inbound email %s", key)
                self.stats.failed += 1
        return processed


# ---------------------------------------------------------------------------
# Singleton for the runtime
# ---------------------------------------------------------------------------


_poller: Optional[InboundEmailPoller] = None
_poller_lock = threading.Lock()


def get_poller() -> Optional[InboundEmailPoller]:
    return _poller


def start_poller(session_factory) -> InboundEmailPoller:
    global _poller
    with _poller_lock:
        if _poller is None:
            _poller = InboundEmailPoller(session_factory=session_factory)
            _poller.start()
    return _poller


def stop_poller() -> None:
    global _poller
    with _poller_lock:
        if _poller is not None:
            _poller.stop()
            _poller = None
