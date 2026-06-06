"""Scheduler API tests.

Hits the FastAPI app via TestClient. The scheduler is disabled in tests
(BRIDGE_OS_DISABLE_SCHEDULER=1 is set in conftest), so we instantiate the
runtime on-demand using the test session DB so endpoints have something
real to talk to.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import ScheduledJob, ScheduledJobRun
from app.scheduler import REGISTRY


class _NoCloseSession:
    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args) -> None:
        return None


@pytest.fixture
def client(db_session: Session) -> TestClient:
    os.environ["BRIDGE_OS_DISABLE_SCHEDULER"] = "1"
    app = create_app()

    from app.db import get_db

    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    # Boot the scheduler manually so /jobs returns the registry
    from app.scheduler.runtime import SchedulerRuntime, _runtime_lock
    import app.scheduler.runtime as rt_mod

    factory = lambda: _NoCloseSession(db_session)

    with _runtime_lock:
        rt_mod._runtime = SchedulerRuntime(session_factory=factory)
        # Seed persistent rows on the test DB
        for spec in REGISTRY:
            if db_session.get(ScheduledJob, spec.name) is None:
                db_session.add(ScheduledJob(name=spec.name, enabled=True))
        db_session.commit()
        rt_mod._runtime._scheduler.start(paused=True)
        for spec in REGISTRY:
            rt_mod._runtime._scheduler.add_job(
                func=lambda: None,
                trigger="interval",
                seconds=3600,
                id=spec.name,
                replace_existing=True,
            )
    try:
        with TestClient(app) as c:
            yield c
    finally:
        with _runtime_lock:
            if rt_mod._runtime is not None:
                try:
                    rt_mod._runtime._scheduler.shutdown(wait=False)
                except Exception:
                    pass
                rt_mod._runtime = None


# ---------------------------------------------------------------------------
# Status + listing
# ---------------------------------------------------------------------------


def test_status_endpoint_reports_jobs(client: TestClient) -> None:
    r = client.get("/system/scheduler/status")
    assert r.status_code == 200
    body = r.json()
    assert body["running"] is True
    assert body["job_count"] == len(REGISTRY)
    assert body["enabled_count"] == len(REGISTRY)
    assert len(body["jobs"]) == len(REGISTRY)


def test_list_jobs(client: TestClient) -> None:
    r = client.get("/system/scheduler/jobs")
    assert r.status_code == 200
    names = {j["name"] for j in r.json()}
    assert "auto_run_cycle" in names
    assert "auto_expire_and_escalate" in names


def test_get_single_job_detail(client: TestClient) -> None:
    r = client.get("/system/scheduler/jobs/auto_run_cycle")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "auto_run_cycle"
    assert "recent_runs" in body
    assert body["enabled"] is True


def test_get_unknown_job_404(client: TestClient) -> None:
    r = client.get("/system/scheduler/jobs/not_a_real_job")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Pause/resume + override
# ---------------------------------------------------------------------------


def test_pause_then_resume(client: TestClient) -> None:
    r = client.post("/system/scheduler/jobs/auto_run_cycle/pause")
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    r = client.post("/system/scheduler/jobs/auto_run_cycle/resume")
    assert r.status_code == 200
    assert r.json()["enabled"] is True


def test_patch_cron_override(client: TestClient) -> None:
    r = client.patch(
        "/system/scheduler/jobs/auto_run_cycle",
        json={"cron_override": "*/2 * * * *"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["cron_override"] == "*/2 * * * *"
    assert r.json()["effective_cron"] == "*/2 * * * *"

    # Clear it back
    r = client.patch(
        "/system/scheduler/jobs/auto_run_cycle",
        json={"clear_override": True},
    )
    assert r.status_code == 200
    assert r.json()["cron_override"] is None


# ---------------------------------------------------------------------------
# Trigger now → writes a run row
# ---------------------------------------------------------------------------


def test_trigger_writes_run_row(client: TestClient, db_session: Session) -> None:
    before = db_session.query(ScheduledJobRun).count()
    r = client.post("/system/scheduler/jobs/auto_run_cycle/trigger")
    assert r.status_code == 200
    assert r.json()["triggered"] is True
    after = db_session.query(ScheduledJobRun).count()
    assert after == before + 1


# ---------------------------------------------------------------------------
# Runs pagination, single, prune
# ---------------------------------------------------------------------------


def test_list_runs_pagination_and_filters(
    client: TestClient, db_session: Session
) -> None:
    # Seed some rows
    now = datetime.utcnow()
    for i in range(7):
        db_session.add(
            ScheduledJobRun(
                job_name="auto_run_cycle",
                started_at=now - timedelta(minutes=i),
                finished_at=now - timedelta(minutes=i) + timedelta(milliseconds=50),
                duration_ms=50.0,
                status="success" if i % 2 == 0 else "failed",
                items_processed=i,
            )
        )
    db_session.commit()

    r = client.get("/system/scheduler/runs?limit=3&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 3
    assert body["total"] >= 7

    r = client.get("/system/scheduler/runs?status=failed")
    assert r.status_code == 200
    assert all(it["status"] == "failed" for it in r.json()["items"])


def test_get_run_returns_payload(client: TestClient, db_session: Session) -> None:
    row = ScheduledJobRun(
        job_name="auto_run_cycle",
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
        duration_ms=12.0,
        status="success",
        items_processed=3,
        payload_json='{"open_slots": 3}',
    )
    db_session.add(row)
    db_session.commit()
    r = client.get(f"/system/scheduler/runs/{row.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["payload"] == {"open_slots": 3}


def test_prune_runs(client: TestClient, db_session: Session) -> None:
    old = datetime.utcnow() - timedelta(days=10)
    db_session.add(
        ScheduledJobRun(
            job_name="auto_run_cycle",
            started_at=old,
            finished_at=old,
            duration_ms=1.0,
            status="success",
            items_processed=0,
        )
    )
    db_session.commit()
    r = client.delete("/system/scheduler/runs?older_than_days=3")
    assert r.status_code == 200
    assert r.json()["deleted"] >= 1


# ---------------------------------------------------------------------------
# Demo mode + metrics + health
# ---------------------------------------------------------------------------


def test_demo_mode_toggle(client: TestClient) -> None:
    r = client.post("/system/scheduler/demo-mode", json={"enabled": True})
    assert r.status_code == 200
    assert r.json()["demo_mode"] is True

    r = client.post("/system/scheduler/demo-mode", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["demo_mode"] is False


def test_metrics_aggregates_by_job(
    client: TestClient, db_session: Session
) -> None:
    now = datetime.utcnow()
    for i in range(4):
        db_session.add(
            ScheduledJobRun(
                job_name="auto_run_cycle",
                started_at=now - timedelta(minutes=i),
                finished_at=now - timedelta(minutes=i),
                duration_ms=10.0 + i,
                status="success",
                items_processed=2,
            )
        )
    db_session.commit()
    r = client.get("/system/scheduler/metrics?window_hours=24")
    assert r.status_code == 200
    body = r.json()
    assert body["window_hours"] == 24
    assert body["overall"]["success"] >= 4
    by_job = {m["job_name"]: m for m in body["by_job"]}
    assert by_job["auto_run_cycle"]["success"] >= 4
    assert by_job["auto_run_cycle"]["avg_duration_ms"] is not None


def test_health_summary_clean(client: TestClient) -> None:
    r = client.get("/system/scheduler/health")
    assert r.status_code == 200
    body = r.json()
    assert body["healthy"] is True
    assert body["issues"] == []
