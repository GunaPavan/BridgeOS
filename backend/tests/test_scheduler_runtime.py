"""Scheduler runtime tests — start/stop/pause/resume/trigger + persistence."""

from __future__ import annotations

import time
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models import ScheduledJob, ScheduledJobRun
from app.scheduler import REGISTRY
from app.scheduler.metrics import JobResult, RUN_STATUS_SUCCESS
from app.scheduler.registry import JobSpec


class _NoCloseSession:
    """Wrap a test session so ``with factory() as db:`` returns the same
    session each time without closing it (the test's ``db_session`` fixture
    owns its lifecycle)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args) -> None:
        # No close — the pytest fixture closes the session at teardown.
        return None


def _test_factory(db_session: Session):
    return lambda: _NoCloseSession(db_session)


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


def test_registry_well_formed() -> None:
    names = [s.name for s in REGISTRY]
    assert len(names) == len(set(names)), "duplicate job names in REGISTRY"
    for spec in REGISTRY:
        assert isinstance(spec, JobSpec)
        assert spec.cron and spec.demo_cron
        # handler_factory must produce a callable
        handler = spec.handler_factory()
        assert callable(handler)


# ---------------------------------------------------------------------------
# record_run context manager
# ---------------------------------------------------------------------------


def test_record_run_success_logs_a_row(db_session: Session) -> None:
    from app.scheduler.metrics import record_run

    db_session.add(ScheduledJob(name="auto_run_cycle", enabled=True))
    db_session.commit()

    with record_run(db_session, job_name="auto_run_cycle") as ctx:
        ctx.set_result(JobResult(items_processed=4, payload={"k": "v"}))

    runs = db_session.query(ScheduledJobRun).all()
    assert len(runs) == 1
    assert runs[0].status == RUN_STATUS_SUCCESS
    assert runs[0].items_processed == 4
    assert '"k": "v"' in (runs[0].payload_json or "")
    # parent row's last_run_at updated
    job = db_session.get(ScheduledJob, "auto_run_cycle")
    assert job.last_run_at is not None


def test_record_run_failure_logs_failed_status_and_reraises(
    db_session: Session,
) -> None:
    from app.scheduler.metrics import record_run

    db_session.add(ScheduledJob(name="auto_run_cycle", enabled=True))
    db_session.commit()

    with pytest.raises(RuntimeError, match="boom"):
        with record_run(db_session, job_name="auto_run_cycle") as _ctx:
            raise RuntimeError("boom")

    runs = db_session.query(ScheduledJobRun).all()
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert "boom" in (runs[0].error_message or "")


def test_record_run_skipped_status(db_session: Session) -> None:
    from app.scheduler.metrics import record_run

    db_session.add(ScheduledJob(name="auto_pending_nudge", enabled=True))
    db_session.commit()

    with record_run(db_session, job_name="auto_pending_nudge") as ctx:
        ctx.set_result(
            JobResult(items_processed=0, skipped_reason="phase_b_not_implemented")
        )

    runs = db_session.query(ScheduledJobRun).all()
    assert runs[0].status == "skipped"
    payload = runs[0].payload_json or ""
    assert "phase_b_not_implemented" in payload


# ---------------------------------------------------------------------------
# Pause/resume persistence — uses runtime against the test session DB
# ---------------------------------------------------------------------------


def test_pause_then_resume_persists_in_db(db_session: Session) -> None:
    """We exercise the runtime functions but stay off APScheduler — pause/resume
    write to the DB synchronously via SessionLocal, which is what we assert."""
    from app.scheduler.runtime import SchedulerRuntime

    # First seed the persistent rows (mimics start() behavior)
    for spec in REGISTRY:
        db_session.add(ScheduledJob(name=spec.name, enabled=True))
    db_session.commit()

    rt = SchedulerRuntime(session_factory=_test_factory(db_session))
    # Hand-fill the APScheduler internals so pause/resume don't fail; we only
    # care about DB state for this test.
    for spec in REGISTRY:
        rt._scheduler.add_job(
            func=lambda: None, trigger="interval", seconds=3600, id=spec.name
        )

    assert rt.pause("auto_run_cycle")
    db_session.expire_all()
    row = db_session.get(ScheduledJob, "auto_run_cycle")
    assert row.enabled is False

    assert rt.resume("auto_run_cycle")
    db_session.expire_all()
    row = db_session.get(ScheduledJob, "auto_run_cycle")
    assert row.enabled is True

    # Unknown job name → False
    assert rt.pause("does_not_exist") is False
    assert rt.resume("does_not_exist") is False


# ---------------------------------------------------------------------------
# Trigger-now invokes the handler synchronously
# ---------------------------------------------------------------------------


def test_trigger_now_invokes_handler_synchronously(db_session: Session) -> None:
    from app.scheduler.runtime import SchedulerRuntime

    db_session.add(ScheduledJob(name="auto_run_cycle", enabled=False))
    db_session.commit()

    rt = SchedulerRuntime(session_factory=_test_factory(db_session))
    ok = rt.trigger_now("auto_run_cycle")
    assert ok

    # Even though the job was disabled, trigger_now fired and logged a run.
    runs = (
        db_session.query(ScheduledJobRun)
        .filter(ScheduledJobRun.job_name == "auto_run_cycle")
        .all()
    )
    assert len(runs) >= 1
