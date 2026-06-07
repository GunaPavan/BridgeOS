"""SQS-backed outbound dispatch queue.

Sits between the allocator and the actual Twilio / SES send.

  engine.dispatch_wave         enqueue
  donor reply ack              ──────►  ┌─────────────┐
  caregiver fallback                    │ SQS dispatch│
                                        │   queue     │
                                        └──────┬──────┘
                                               │ poll (long)
                                               ▼
                                        DispatchWorker thread
                                               │
                                          ┌────┴────┐
                                          ▼         ▼
                                     twilio_client  ses_client
                                     (whatsapp)     (email)

WHY THIS EXISTS
---------------
Today engine.dispatch_wave calls twilio_client.send_whatsapp inline. If the
Twilio API takes 5 seconds, the allocator cycle blocks for 5s × batch_size.
By writing to SQS and letting a worker drain asynchronously, the allocator
ticks at constant time and outbound throughput scales independently.

IDEMPOTENCY
-----------
Every envelope carries an ``idempotency_key`` (typically ``dispatch_{ping_id}``).
The worker checks the relevant DB row before sending — if the ping is
already marked sent (or the email already in EmailMessage), the message is
dropped without a duplicate send.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.integrations import sqs_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


@dataclass
class DispatchEnvelope:
    """Self-contained payload — the worker doesn't need to look anything up
    in the DB to send (though it WILL check idempotency before sending)."""

    channel: str   # "sms" | "whatsapp" | "email"
    to: str
    body: str
    idempotency_key: str
    # Optional metadata so the worker can update the right DB row
    ping_id: Optional[str] = None
    template_key: Optional[str] = None
    language: Optional[str] = None
    subject: Optional[str] = None
    # Caregiver/donor attribution for EmailMessage rows
    donor_id: Optional[str] = None
    caregiver_for_patient_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DispatchEnvelope":
        # Drop any keys we don't recognise so old envelopes don't break new code
        valid = {k: v for k, v in d.items() if k in {
            "channel", "to", "body", "idempotency_key", "ping_id",
            "template_key", "language", "subject", "donor_id",
            "caregiver_for_patient_id",
        }}
        return cls(**valid)


# ---------------------------------------------------------------------------
# Public publisher used by engine + dispatchers
# ---------------------------------------------------------------------------


def enqueue_dispatch(env: DispatchEnvelope) -> str:
    """Publish a single envelope. Returns the message id."""
    res = sqs_client.publish(env.to_dict())
    logger.info(
        "enqueued %s dispatch to %s (id=%s, key=%s)",
        env.channel, env.to, res.message_id, env.idempotency_key,
    )
    return res.message_id


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


@dataclass
class WorkerStats:
    received: int = 0
    sent: int = 0
    duplicates_skipped: int = 0
    failed: int = 0
    last_drained_at: Optional[datetime] = None
    started_at: Optional[datetime] = None


class DispatchWorker:
    """Long-running thread that drains the SQS dispatch queue and sends.

    Started by ``SchedulerRuntime.start()``. Stopped cleanly on shutdown.
    """

    def __init__(self, *, session_factory, poll_interval_seconds: float = 1.0) -> None:
        self._SessionLocal = session_factory
        self._poll_interval = poll_interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.stats = WorkerStats()

    # ----- lifecycle -----

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self.stats.started_at = datetime.utcnow()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="DispatchWorker")
        self._thread.start()
        logger.info("DispatchWorker started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("DispatchWorker stopped")

    # ----- main loop -----

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._drain_once()
            except Exception:  # pragma: no cover — defensive
                logger.exception("DispatchWorker drain raised")
            # Don't busy-loop in mock mode (live mode uses long-poll for the wait)
            self._stop.wait(self._poll_interval)

    def _drain_once(self, *, batch: int = 10) -> int:
        """Pull a batch, process each. Returns count processed."""
        # In live mode we long-poll for 20s; in mock mode this returns immediately.
        msgs = sqs_client.receive_messages(max_messages=batch, wait_seconds=10)
        if not msgs:
            return 0

        with self._SessionLocal() as db:
            for m in msgs:
                self.stats.received += 1
                try:
                    env = DispatchEnvelope.from_dict(m.body)
                except Exception:
                    logger.exception("Malformed envelope, dropping: %s", m.body)
                    sqs_client.delete_message(receipt_handle=m.receipt_handle)
                    self.stats.failed += 1
                    continue

                if self._already_dispatched(db, env):
                    sqs_client.delete_message(receipt_handle=m.receipt_handle)
                    self.stats.duplicates_skipped += 1
                    continue

                ok = self._dispatch(db, env)
                if ok:
                    sqs_client.delete_message(receipt_handle=m.receipt_handle)
                    self.stats.sent += 1
                else:
                    # Leave the message — visibility timeout will resurface it
                    self.stats.failed += 1

        self.stats.last_drained_at = datetime.utcnow()
        try:
            db.commit()
        except Exception:  # pragma: no cover
            logger.exception("Commit failed in DispatchWorker drain")
        return len(msgs)

    # ----- helpers -----

    def _already_dispatched(self, db: Session, env: DispatchEnvelope) -> bool:
        """Idempotency check.

        - For WhatsApp pings: ping has a Twilio SID already → already sent.
        - For emails: an EmailMessage row with the same idempotency_key →
          already sent. (We don't have an idempotency_key column yet — for
          now check by recipient + subject sent in the last 30 seconds.)
        """
        from app.models import OutreachPing

        if env.channel in ("whatsapp", "sms") and env.ping_id:
            try:
                ping = db.get(OutreachPing, uuid.UUID(env.ping_id))
            except Exception:
                ping = None
            if ping and ping.whatsapp_sid:
                return True
        return False

    def _dispatch(self, db: Session, env: DispatchEnvelope) -> bool:
        if env.channel == "sms":
            return self._dispatch_sms(db, env)
        if env.channel == "whatsapp":
            return self._dispatch_whatsapp(db, env)
        if env.channel == "email":
            return self._dispatch_email(db, env)
        logger.warning("Unknown dispatch channel: %s", env.channel)
        return False

    def _dispatch_sms(self, db: Session, env: DispatchEnvelope) -> bool:
        """Send via SNS direct-SMS.

        SMS is **one-way** — AWS doesn't offer free inbound India SMS. So
        before sending, we append a "call coordinator on +91..." tail to
        the body so the recipient knows where to direct their response.
        (The original ``body`` rendered as if it were a reply-able message
        because dispatch_wave uses the same template for all channels.)

        Mirrors the message into ``WhatsAppMessage`` (yes, the table name
        is misleading — it's our generic outbound channel log) so the
        existing donor-thread UI surfaces SMS sends too.
        """
        from app.integrations import sns_sms_client
        from app.models import (
            MessageDirection,
            MessageStatus,
            OutreachPing,
            WhatsAppMessage,
        )

        # Append the call-back tail unless the body already has it.
        # Coordinator phone comes from BRIDGE_OS_COORDINATOR_PHONE — set via
        # Secrets Manager in prod, the local .env in dev. Skipped silently
        # when unset so dev SMS doesn't ship a stale placeholder number.
        body_to_send = env.body
        coordinator_phone = os.environ.get("BRIDGE_OS_COORDINATOR_PHONE", "").strip()
        if coordinator_phone and "call coordinator" not in body_to_send.lower():
            body_to_send = (
                f"{body_to_send}\n\nCan't reply? Call coordinator at {coordinator_phone}."
            )

        try:
            result = sns_sms_client.send_sms(to_number=env.to, body=body_to_send)
        except Exception:
            logger.exception("SNS SMS dispatch failed for %s", env.idempotency_key)
            return False

        # Stamp the ping (we reuse whatsapp_sid for SMS too — it's effectively
        # an external message id from any channel)
        bridge_id = None
        if env.ping_id:
            try:
                ping = db.get(OutreachPing, uuid.UUID(env.ping_id))
            except Exception:
                ping = None
            if ping is not None:
                ping.whatsapp_sid = result.message_id
                ping.template_key = env.template_key or ping.template_key
                ping.language = env.language or ping.language
                if not ping.sent_at:
                    ping.sent_at = datetime.utcnow()
                if ping.wave is not None:
                    bridge_id = ping.wave.bridge_id

        status = (
            MessageStatus(result.status)
            if result.status in {s.value for s in MessageStatus}
            else MessageStatus.QUEUED
        )
        db.add(
            WhatsAppMessage(
                donor_id=uuid.UUID(env.donor_id) if env.donor_id else None,
                bridge_id=bridge_id,
                direction=MessageDirection.OUTBOUND,
                from_number="sms:BLDWAR",
                to_number=env.to,
                body=body_to_send,  # what we actually sent, including the call-back tail
                status=status,
                twilio_sid=result.message_id,
                template_key=env.template_key,
                language=env.language,
            )
        )
        return result.status in ("sent", "mocked")

    def _dispatch_whatsapp(self, db: Session, env: DispatchEnvelope) -> bool:
        from app.integrations import twilio_client
        from app.models import (
            MessageDirection,
            MessageStatus,
            OutreachPing,
            WhatsAppMessage,
        )

        try:
            result = twilio_client.send_whatsapp(to_number=env.to, body=env.body)
        except Exception:
            logger.exception("Twilio dispatch failed for %s", env.idempotency_key)
            return False

        # Stamp the ping
        if env.ping_id:
            try:
                ping = db.get(OutreachPing, uuid.UUID(env.ping_id))
            except Exception:
                ping = None
            if ping is not None:
                ping.whatsapp_sid = result.sid
                ping.template_key = env.template_key or ping.template_key
                ping.language = env.language or ping.language
                if not ping.sent_at:
                    ping.sent_at = datetime.utcnow()

        # Mirror into WhatsAppMessage so /whatsapp shows the thread
        status = (
            MessageStatus(result.status)
            if result.status in {s.value for s in MessageStatus}
            else MessageStatus.QUEUED
        )
        bridge_id = None
        if env.ping_id:
            try:
                ping = db.get(OutreachPing, uuid.UUID(env.ping_id))
                if ping is not None and ping.wave is not None:
                    bridge_id = ping.wave.bridge_id
            except Exception:
                pass
        db.add(
            WhatsAppMessage(
                donor_id=uuid.UUID(env.donor_id) if env.donor_id else None,
                bridge_id=bridge_id,
                direction=MessageDirection.OUTBOUND,
                from_number=twilio_client.whatsapp_from(),
                to_number=env.to,
                body=env.body,
                status=status,
                twilio_sid=result.sid,
                template_key=env.template_key,
                language=env.language,
            )
        )
        return True

    def _dispatch_email(self, db: Session, env: DispatchEnvelope) -> bool:
        from app.integrations import ses_client
        from app.models import EmailMessage

        result = ses_client.send_email(
            to=env.to, subject=env.subject or "", body=env.body
        )
        now = datetime.utcnow()
        db.add(
            EmailMessage(
                direction="outbound",
                recipient_email=env.to,
                from_email=ses_client.from_email(),
                subject=env.subject or "",
                body=env.body,
                template_key=env.template_key,
                language=env.language or "en",
                ses_message_id=result.message_id,
                status=result.status,
                is_mock=result.is_mock,
                error_message=result.error_message,
                donor_id=uuid.UUID(env.donor_id) if env.donor_id else None,
                caregiver_for_patient_id=(
                    uuid.UUID(env.caregiver_for_patient_id)
                    if env.caregiver_for_patient_id
                    else None
                ),
                created_at=now,
                sent_at=now if result.status in ("sent", "mocked") else None,
            )
        )
        return result.status in ("sent", "mocked")


# ---------------------------------------------------------------------------
# Singleton accessor for the runtime to hold + the API to introspect
# ---------------------------------------------------------------------------


_worker: Optional[DispatchWorker] = None
_worker_lock = threading.Lock()


def get_worker() -> Optional[DispatchWorker]:
    return _worker


def start_worker(session_factory) -> DispatchWorker:
    """Start the singleton DispatchWorker. Idempotent."""
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = DispatchWorker(session_factory=session_factory)
            _worker.start()
    return _worker


def stop_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is not None:
            _worker.stop()
            _worker = None
