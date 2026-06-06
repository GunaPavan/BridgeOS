"""Phase D — metrics aggregation + extended /system/health checks."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ScheduledJobRun


# ---------------------------------------------------------------------------
# /system/scheduler/metrics
# ---------------------------------------------------------------------------


def _seed_runs(db: Session, *, job_name: str, durations: list[float], status: str = "success") -> None:
    now = datetime.utcnow()
    for i, d in enumerate(durations):
        db.add(
            ScheduledJobRun(
                job_name=job_name,
                started_at=now - timedelta(minutes=i),
                finished_at=now - timedelta(minutes=i),
                duration_ms=d,
                status=status,
                items_processed=1,
            )
        )
    db.commit()


def test_metrics_returns_p50_and_p95(
    client: TestClient, db_session: Session
) -> None:
    _seed_runs(
        db_session,
        job_name="auto_run_cycle",
        durations=[10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0],
    )
    r = client.get("/system/scheduler/metrics?window_hours=24")
    assert r.status_code == 200
    body = r.json()
    by_job = {m["job_name"]: m for m in body["by_job"]}
    metric = by_job["auto_run_cycle"]
    assert metric["avg_duration_ms"] == 55.0
    # p50 of 10..100 with our percentile picker is one of {50, 60} (rank 4 of 9)
    assert metric["p50_duration_ms"] in (50.0, 60.0)
    assert metric["p95_duration_ms"] in (90.0, 100.0)


def test_metrics_groups_by_status(
    client: TestClient, db_session: Session
) -> None:
    _seed_runs(db_session, job_name="auto_run_cycle", durations=[10.0, 20.0], status="success")
    _seed_runs(db_session, job_name="auto_run_cycle", durations=[5.0], status="failed")
    _seed_runs(db_session, job_name="auto_run_cycle", durations=[1.0], status="skipped")

    body = client.get("/system/scheduler/metrics?window_hours=24").json()
    by_job = {m["job_name"]: m for m in body["by_job"]}
    assert by_job["auto_run_cycle"]["success"] == 2
    assert by_job["auto_run_cycle"]["failed"] == 1
    assert by_job["auto_run_cycle"]["skipped"] == 1
    assert body["overall"]["success"] == 2
    assert body["overall"]["failed"] == 1


def test_metrics_window_respected(
    client: TestClient, db_session: Session
) -> None:
    now = datetime.utcnow()
    # 30 hours ago — outside the 24h window
    db_session.add(
        ScheduledJobRun(
            job_name="auto_run_cycle",
            started_at=now - timedelta(hours=30),
            finished_at=now - timedelta(hours=30),
            duration_ms=10.0,
            status="success",
            items_processed=1,
        )
    )
    db_session.commit()
    body = client.get("/system/scheduler/metrics?window_hours=24").json()
    assert body["overall"]["success"] == 0


# ---------------------------------------------------------------------------
# /system/scheduler/health — failure streaks
# ---------------------------------------------------------------------------


def test_health_flags_consecutive_failures(
    client: TestClient, db_session: Session
) -> None:
    # Two failures in a row — should surface as an issue
    _seed_runs(
        db_session,
        job_name="auto_run_cycle",
        durations=[1.0, 1.0],
        status="failed",
    )
    body = client.get("/system/scheduler/health").json()
    assert body["healthy"] is False
    assert any("auto_run_cycle" in i for i in body["issues"])
    assert body["failure_streaks"]["auto_run_cycle"] >= 2


def test_health_recent_success_resets_streak(
    client: TestClient, db_session: Session
) -> None:
    # Most recent run is success → streak should be 0 even with old failures
    now = datetime.utcnow()
    db_session.add_all(
        [
            ScheduledJobRun(
                job_name="auto_run_cycle",
                started_at=now - timedelta(minutes=10),
                finished_at=now - timedelta(minutes=10),
                duration_ms=1.0,
                status="failed",
            ),
            ScheduledJobRun(
                job_name="auto_run_cycle",
                started_at=now - timedelta(minutes=5),
                finished_at=now - timedelta(minutes=5),
                duration_ms=1.0,
                status="failed",
            ),
            ScheduledJobRun(
                job_name="auto_run_cycle",
                started_at=now,
                finished_at=now,
                duration_ms=1.0,
                status="success",
            ),
        ]
    )
    db_session.commit()
    body = client.get("/system/scheduler/health").json()
    assert body["failure_streaks"]["auto_run_cycle"] == 0
    assert body["healthy"] is True


# ---------------------------------------------------------------------------
# /system/health/full
# ---------------------------------------------------------------------------


def test_full_health_reports_db_scheduler_bedrock_twilio(
    client: TestClient,
) -> None:
    r = client.get("/system/health/full")
    assert r.status_code == 200
    body = r.json()
    for key in ("db", "scheduler", "bedrock", "twilio", "warnings", "healthy", "checked_at"):
        assert key in body
    assert body["db"]["ok"] is True
    # Bedrock + Twilio aren't configured in tests → warnings list contains them
    assert any("bedrock" in w for w in body["warnings"])
    assert any("twilio" in w for w in body["warnings"])
