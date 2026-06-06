"""APScheduler wrapper that turns the JobSpec registry into running cron jobs.

The runtime is a singleton — one ``SchedulerRuntime`` per process. FastAPI's
lifespan hook calls ``start_scheduler()`` once at startup and
``stop_scheduler()`` once at shutdown.

Design rules:

  • Each tick gets its OWN db Session (created from SessionLocal). We never
    share a session across job runs.

  • Per-job state lives in the ``ScheduledJob`` table. ``upsert_specs()``
    runs at start time and INSERTs new rows for first-time jobs while
    leaving existing (enabled, cron_override) state alone.

  • Pausing a job updates ``ScheduledJob.enabled = False`` and removes
    the APScheduler job; resuming reverses both.

  • Demo mode swaps EVERY job to its compressed ``demo_cron``. The flag
    is held in-memory (we don't persist demo-mode because it's a session-
    level affordance, not a configuration).

  • ``trigger_now(name)`` ignores the pause flag — useful for the demo
    "Run now" button.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.db import SessionLocal as _DefaultSessionLocal
from app.models import ScheduledJob
from app.scheduler.metrics import record_run
from app.scheduler.registry import REGISTRY, JobSpec, get_spec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Singleton accessors
# ---------------------------------------------------------------------------


_runtime: Optional["SchedulerRuntime"] = None
_runtime_lock = threading.Lock()


def get_scheduler() -> Optional["SchedulerRuntime"]:
    return _runtime


def start_scheduler() -> "SchedulerRuntime":
    """Idempotent — multiple calls return the same instance."""
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = SchedulerRuntime()
            _runtime.start()
        return _runtime


def stop_scheduler() -> None:
    global _runtime
    with _runtime_lock:
        if _runtime is not None:
            _runtime.stop()
            _runtime = None


# ---------------------------------------------------------------------------
# The runtime itself
# ---------------------------------------------------------------------------


class SchedulerRuntime:
    """Owns the APScheduler instance and the demo-mode flag.

    Public API: ``start``, ``stop``, ``pause(name)``, ``resume(name)``,
    ``trigger_now(name)``, ``set_demo_mode(bool)``, ``status()``.
    """

    def __init__(self, session_factory=None) -> None:
        """``session_factory`` is a context-manager-yielding callable that
        returns a new SQLAlchemy Session. Defaults to ``app.db.SessionLocal``
        in production; tests inject a factory wired to the in-memory test DB.
        """
        self._scheduler = BackgroundScheduler(
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60},
        )
        self._demo_mode: bool = False
        self._SessionLocal = session_factory or _DefaultSessionLocal

    # ----- lifecycle -----

    def start(self) -> None:
        with self._SessionLocal() as db:
            self._upsert_specs(db)
        for spec in REGISTRY:
            self._register_job_if_enabled(spec)
        self._scheduler.start()
        # Phase E3: start the SQS dispatch worker alongside the scheduler so
        # outbound messages flow as soon as engine.dispatch_wave enqueues.
        try:
            from app.outreach.dispatch_queue import start_worker as _start_dispatch

            _start_dispatch(self._SessionLocal)
        except Exception:  # pragma: no cover
            logger.exception("Failed to start SQS DispatchWorker")
        # Phase E4: start the SNS event dispatcher so subscribers fire on
        # every published donor-reply / wave event.
        try:
            from app.events import start_dispatcher as _start_events

            _start_events(self._SessionLocal)
        except Exception:  # pragma: no cover
            logger.exception("Failed to start EventDispatcher")
        # Phase E8: start the SES inbound poller (drains S3 bucket of real
        # caregiver email replies). No-ops if AWS isn't configured.
        try:
            from app.outreach.inbound_email_poller import (
                start_poller as _start_inbound,
            )

            _start_inbound(self._SessionLocal)
        except Exception:  # pragma: no cover
            logger.exception("Failed to start InboundEmailPoller")
        logger.info("SchedulerRuntime started with %d jobs", len(REGISTRY))

    def stop(self) -> None:
        try:
            from app.outreach.dispatch_queue import stop_worker as _stop_dispatch

            _stop_dispatch()
        except Exception:  # pragma: no cover
            logger.exception("Stop dispatch worker failed")
        try:
            from app.events import stop_dispatcher as _stop_events

            _stop_events()
        except Exception:  # pragma: no cover
            logger.exception("Stop event dispatcher failed")
        try:
            from app.outreach.inbound_email_poller import stop_poller as _stop_inbound

            _stop_inbound()
        except Exception:  # pragma: no cover
            logger.exception("Stop inbound email poller failed")
        try:
            self._scheduler.shutdown(wait=False)
        except Exception:  # pragma: no cover — best-effort shutdown
            logger.exception("SchedulerRuntime shutdown raised")

    # ----- upsert from registry -----

    def _upsert_specs(self, db: Session) -> None:
        """First-run: create a ScheduledJob row for any new spec. Keep state
        for jobs that already exist (pause + cron_override survive restarts).
        """
        existing = {row.name: row for row in db.query(ScheduledJob).all()}
        for spec in REGISTRY:
            if spec.name not in existing:
                db.add(
                    ScheduledJob(
                        name=spec.name,
                        enabled=spec.default_enabled,
                        cron_override=None,
                    )
                )
        db.commit()

    # ----- per-job (re)registration -----

    def _register_job_if_enabled(self, spec: JobSpec) -> None:
        """Add the APScheduler job IF the persisted state says enabled.

        Effective cron precedence: cron_override > demo_cron > spec.cron.
        """
        with self._SessionLocal() as db:
            row = db.get(ScheduledJob, spec.name)
            if row is None or not row.enabled:
                return
            cron_expr = self._effective_cron(spec, row)

        trigger = self._build_trigger(cron_expr)
        self._scheduler.add_job(
            func=self._wrap_handler(spec),
            trigger=trigger,
            id=spec.name,
            name=spec.name,
            replace_existing=True,
        )
        logger.info("Registered job %s with cron=%r", spec.name, cron_expr)

    def _effective_cron(self, spec: JobSpec, row: ScheduledJob) -> str:
        if row.cron_override:
            return row.cron_override
        return spec.demo_cron if self._demo_mode else spec.cron

    def _build_trigger(self, cron_expr: str) -> CronTrigger:
        """Accept either 5-field (m h dom mon dow) or 6-field (s m h dom mon dow)
        cron expressions. APScheduler picks which fields apply by count."""
        parts = cron_expr.split()
        if len(parts) == 5:
            return CronTrigger.from_crontab(cron_expr)
        if len(parts) == 6:
            second, minute, hour, day, month, day_of_week = parts
            return CronTrigger(
                second=second,
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
            )
        raise ValueError(f"Unparseable cron expression: {cron_expr!r}")

    # ----- handler wrapper -----

    def _wrap_handler(self, spec: JobSpec):
        """Build the actual callable APScheduler will fire.

        Each tick: fresh db session, fresh ``now``, record_run() context
        manager wraps the handler call so success + failure both write an
        audit row.
        """
        handler = spec.handler_factory()
        job_name = spec.name

        def _tick() -> None:
            with self._SessionLocal() as db:
                # Skip if the job has been paused since registration.
                row = db.get(ScheduledJob, job_name)
                if row is None or not row.enabled:
                    return
                now = datetime.utcnow()
                with record_run(db, job_name=job_name) as ctx:
                    result = handler(db=db, now=now)
                    ctx.set_result(result)

        return _tick

    # ----- pause/resume/trigger -----

    def pause(self, name: str) -> bool:
        """Returns True if the job exists and was paused; False if unknown."""
        spec = get_spec(name)
        if spec is None:
            return False
        with self._SessionLocal() as db:
            row = db.get(ScheduledJob, name)
            if row is None:
                return False
            row.enabled = False
            db.commit()
        try:
            self._scheduler.remove_job(name)
        except Exception:
            pass  # job might not have been registered yet
        return True

    def resume(self, name: str) -> bool:
        spec = get_spec(name)
        if spec is None:
            return False
        with self._SessionLocal() as db:
            row = db.get(ScheduledJob, name)
            if row is None:
                row = ScheduledJob(name=name, enabled=True)
                db.add(row)
            row.enabled = True
            db.commit()
        self._register_job_if_enabled(spec)
        return True

    def trigger_now(self, name: str) -> bool:
        """Fire the handler immediately, bypassing the pause flag.

        Even if the job is paused, this single invocation runs. Useful for
        the "Run now" demo button.
        """
        spec = get_spec(name)
        if spec is None:
            return False
        handler = spec.handler_factory()
        with self._SessionLocal() as db:
            now = datetime.utcnow()
            with record_run(db, job_name=name) as ctx:
                result = handler(db=db, now=now)
                ctx.set_result(result)
        return True

    # ----- demo mode -----

    def set_demo_mode(self, enabled: bool) -> None:
        """Re-register every job with its new (compressed or normal) cron."""
        if self._demo_mode == enabled:
            return
        self._demo_mode = enabled
        for spec in REGISTRY:
            try:
                self._scheduler.remove_job(spec.name)
            except Exception:
                pass
        for spec in REGISTRY:
            self._register_job_if_enabled(spec)
        logger.info("Demo mode set to %s", enabled)

    @property
    def demo_mode(self) -> bool:
        return self._demo_mode

    # ----- introspection -----

    def status(self) -> dict:
        ap_jobs = {j.id: j for j in self._scheduler.get_jobs()}
        out_jobs = []
        with self._SessionLocal() as db:
            persisted = {r.name: r for r in db.query(ScheduledJob).all()}
        for spec in REGISTRY:
            row = persisted.get(spec.name)
            ap = ap_jobs.get(spec.name)
            out_jobs.append(
                {
                    "name": spec.name,
                    "description": spec.description,
                    "enabled": bool(row.enabled) if row else spec.default_enabled,
                    "cron_default": spec.cron,
                    "cron_demo": spec.demo_cron,
                    "cron_override": row.cron_override if row else None,
                    "effective_cron": (
                        self._effective_cron(spec, row) if row else spec.cron
                    ),
                    "last_run_at": (
                        row.last_run_at.isoformat() + "Z"
                        if row and row.last_run_at
                        else None
                    ),
                    "next_run_at": (
                        ap.next_run_time.isoformat()
                        if ap and ap.next_run_time
                        else None
                    ),
                }
            )
        return {
            "running": self._scheduler.running,
            "demo_mode": self._demo_mode,
            "jobs": out_jobs,
        }
