"""``/system/scheduler/*`` — full CRUD over the Automation Engine.

Read the registry, pause/resume/trigger jobs, page through run history,
prune old audit rows, flip demo mode. The runtime is owned by
``app.scheduler.runtime`` — this module is a thin HTTP adapter.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, delete, desc, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ScheduledJob, ScheduledJobRun
from app.scheduler import REGISTRY, get_scheduler
from app.scheduler.metrics import RUN_STATUS_FAILED, RUN_STATUS_SUCCESS
from app.scheduler.registry import get_spec
from app.schemas.scheduler import (
    DemoModeRequest,
    HealthSummary,
    JobDetail,
    JobMetric,
    JobState,
    JobUpdateRequest,
    PruneResult,
    RunDetail,
    RunSummary,
    RunsPage,
    SchedulerMetrics,
    SchedulerStatus,
    TriggerResult,
)

router = APIRouter(prefix="/system/scheduler", tags=["scheduler"])


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def _failures_in_window(db: Session, hours: int) -> int:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    return (
        db.execute(
            select(func.count(ScheduledJobRun.id)).where(
                and_(
                    ScheduledJobRun.status == RUN_STATUS_FAILED,
                    ScheduledJobRun.started_at >= cutoff,
                )
            )
        ).scalar_one()
        or 0
    )


@router.get(
    "/status",
    response_model=SchedulerStatus,
    summary="Overall scheduler health snapshot",
)
def get_status(db: Session = Depends(get_db)) -> SchedulerStatus:
    runtime = get_scheduler()
    if runtime is None:
        # Scheduler is not running — still answer with a healthy-shaped
        # response so the UI can render "off" instead of erroring.
        return SchedulerStatus(
            running=False,
            demo_mode=False,
            job_count=len(REGISTRY),
            enabled_count=0,
            last_tick_at=None,
            failures_24h=0,
            jobs=[],
        )
    raw = runtime.status()
    jobs = [JobState(**j) for j in raw["jobs"]]
    last_tick = (
        db.execute(
            select(func.max(ScheduledJobRun.finished_at)).where(
                ScheduledJobRun.status == RUN_STATUS_SUCCESS
            )
        ).scalar_one()
    )
    return SchedulerStatus(
        running=raw["running"],
        demo_mode=raw["demo_mode"],
        job_count=len(jobs),
        enabled_count=sum(1 for j in jobs if j.enabled),
        last_tick_at=last_tick,
        failures_24h=_failures_in_window(db, 24),
        jobs=jobs,
    )


# ---------------------------------------------------------------------------
# Jobs CRUD
# ---------------------------------------------------------------------------


def _job_state_for(name: str) -> JobState:
    """Build a JobState for one job by name. 404s if the name isn't in the
    registry."""
    runtime = get_scheduler()
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler is not running.",
        )
    raw = runtime.status()
    for j in raw["jobs"]:
        if j["name"] == name:
            return JobState(**j)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job '{name}'."
    )


@router.get("/jobs", response_model=list[JobState], summary="List all jobs")
def list_jobs() -> list[JobState]:
    runtime = get_scheduler()
    if runtime is None:
        return []
    return [JobState(**j) for j in runtime.status()["jobs"]]


@router.get(
    "/jobs/{name}",
    response_model=JobDetail,
    summary="Single job detail + recent run history",
)
def get_job(
    name: str,
    recent_runs: int = Query(10, ge=0, le=100),
    db: Session = Depends(get_db),
) -> JobDetail:
    state = _job_state_for(name)
    rows = (
        db.execute(
            select(ScheduledJobRun)
            .where(ScheduledJobRun.job_name == name)
            .order_by(desc(ScheduledJobRun.started_at))
            .limit(recent_runs)
        )
        .scalars()
        .all()
    )
    return JobDetail(
        **state.model_dump(),
        recent_runs=[RunSummary.model_validate(r, from_attributes=True) for r in rows],
    )


@router.patch(
    "/jobs/{name}",
    response_model=JobState,
    summary="Update job — set or clear the cron_override",
)
def update_job(
    name: str,
    body: JobUpdateRequest,
    db: Session = Depends(get_db),
) -> JobState:
    if get_spec(name) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job '{name}'."
        )
    row = db.get(ScheduledJob, name)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{name}' has no persisted row yet (server still starting?).",
        )

    if body.clear_override:
        row.cron_override = None
    elif body.cron_override is not None:
        row.cron_override = body.cron_override
    db.commit()

    # Re-register so APScheduler picks up the new cron right away
    runtime = get_scheduler()
    if runtime is not None and row.enabled:
        runtime.resume(name)  # safe — resume re-registers with effective cron
    return _job_state_for(name)


@router.post(
    "/jobs/{name}/pause",
    response_model=JobState,
    summary="Pause a job — survives restarts",
)
def pause_job(name: str) -> JobState:
    runtime = get_scheduler()
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler is not running.",
        )
    if not runtime.pause(name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job '{name}'."
        )
    return _job_state_for(name)


@router.post(
    "/jobs/{name}/resume",
    response_model=JobState,
    summary="Resume a paused job",
)
def resume_job(name: str) -> JobState:
    runtime = get_scheduler()
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler is not running.",
        )
    if not runtime.resume(name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job '{name}'."
        )
    return _job_state_for(name)


@router.post(
    "/jobs/{name}/trigger",
    response_model=TriggerResult,
    summary="Fire the job once now (bypasses pause)",
)
def trigger_job(name: str) -> TriggerResult:
    runtime = get_scheduler()
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler is not running.",
        )
    ok = runtime.trigger_now(name)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job '{name}'."
        )
    return TriggerResult(job_name=name, triggered=True)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@router.get(
    "/runs",
    response_model=RunsPage,
    summary="Paginated audit log of every job execution",
)
def list_runs(
    job: Optional[str] = Query(None, description="Filter by job name"),
    run_status: Optional[str] = Query(
        None, alias="status", description="success|failed|skipped"
    ),
    since_hours: Optional[int] = Query(None, ge=1, le=168),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> RunsPage:
    where = []
    if job:
        where.append(ScheduledJobRun.job_name == job)
    if run_status:
        where.append(ScheduledJobRun.status == run_status)
    if since_hours:
        cutoff = datetime.utcnow() - timedelta(hours=since_hours)
        where.append(ScheduledJobRun.started_at >= cutoff)

    count_stmt = select(func.count(ScheduledJobRun.id))
    list_stmt = select(ScheduledJobRun).order_by(desc(ScheduledJobRun.started_at))
    if where:
        from sqlalchemy import and_ as _and

        count_stmt = count_stmt.where(_and(*where))
        list_stmt = list_stmt.where(_and(*where))

    total = db.execute(count_stmt).scalar_one() or 0
    rows = db.execute(list_stmt.offset(offset).limit(limit)).scalars().all()
    return RunsPage(
        items=[RunSummary.model_validate(r, from_attributes=True) for r in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/runs/{run_id}",
    response_model=RunDetail,
    summary="Single run (includes payload)",
)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db)) -> RunDetail:
    row = db.get(ScheduledJobRun, run_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
        )
    import json

    payload = json.loads(row.payload_json) if row.payload_json else None
    return RunDetail(
        id=row.id,
        job_name=row.job_name,
        started_at=row.started_at,
        finished_at=row.finished_at,
        duration_ms=row.duration_ms,
        status=row.status,
        items_processed=row.items_processed,
        error_message=row.error_message,
        payload=payload,
    )


@router.delete(
    "/runs",
    response_model=PruneResult,
    summary="Prune audit rows older than N days",
)
def prune_runs(
    older_than_days: int = Query(..., ge=1, le=365),
    db: Session = Depends(get_db),
) -> PruneResult:
    cutoff = datetime.utcnow() - timedelta(days=older_than_days)
    result = db.execute(
        delete(ScheduledJobRun).where(ScheduledJobRun.started_at < cutoff)
    )
    db.commit()
    return PruneResult(deleted=int(result.rowcount or 0))


# ---------------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------------


@router.post(
    "/demo-mode",
    response_model=SchedulerStatus,
    summary="Toggle compressed cadences for live demo",
)
def set_demo_mode(
    body: DemoModeRequest, db: Session = Depends(get_db)
) -> SchedulerStatus:
    runtime = get_scheduler()
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler is not running.",
        )
    runtime.set_demo_mode(body.enabled)
    return get_status(db=db)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _percentile(values: list[float], p: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1)))))
    return round(s[idx], 3)


@router.get(
    "/metrics",
    response_model=SchedulerMetrics,
    summary="Aggregated counts by job × status over a window",
)
def get_metrics(
    window_hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> SchedulerMetrics:
    cutoff = datetime.utcnow() - timedelta(hours=window_hours)
    rows = (
        db.execute(
            select(ScheduledJobRun).where(ScheduledJobRun.started_at >= cutoff)
        )
        .scalars()
        .all()
    )
    by_job_map: dict[str, JobMetric] = {}
    durations_by_job: dict[str, list[float]] = {}
    overall = {"success": 0, "failed": 0, "skipped": 0, "items_processed_total": 0}
    for r in rows:
        m = by_job_map.setdefault(r.job_name, JobMetric(job_name=r.job_name))
        if r.status == "success":
            m.success += 1
            overall["success"] += 1
        elif r.status == "failed":
            m.failed += 1
            overall["failed"] += 1
        else:
            m.skipped += 1
            overall["skipped"] += 1
        m.items_processed_total += int(r.items_processed or 0)
        overall["items_processed_total"] += int(r.items_processed or 0)
        if r.duration_ms is not None:
            durations_by_job.setdefault(r.job_name, []).append(float(r.duration_ms))
    for name, m in by_job_map.items():
        ds = durations_by_job.get(name, [])
        if ds:
            m.avg_duration_ms = round(sum(ds) / len(ds), 3)
            m.p50_duration_ms = _percentile(ds, 50)
            m.p95_duration_ms = _percentile(ds, 95)
    return SchedulerMetrics(
        window_hours=window_hours,
        overall=overall,
        by_job=sorted(by_job_map.values(), key=lambda x: x.job_name),
    )


@router.get(
    "/health",
    response_model=HealthSummary,
    summary="Boolean health + per-job failure streaks",
)
def get_health(db: Session = Depends(get_db)) -> HealthSummary:
    streaks: dict[str, int] = {}
    issues: list[str] = []
    for spec in REGISTRY:
        recent = (
            db.execute(
                select(ScheduledJobRun)
                .where(ScheduledJobRun.job_name == spec.name)
                .order_by(desc(ScheduledJobRun.started_at))
                .limit(5)
            )
            .scalars()
            .all()
        )
        streak = 0
        for r in recent:
            if r.status == RUN_STATUS_FAILED:
                streak += 1
            else:
                break
        streaks[spec.name] = streak
        if streak >= 2:
            issues.append(f"{spec.name}: {streak} failures in a row")
    last_tick = (
        db.execute(
            select(func.max(ScheduledJobRun.finished_at)).where(
                ScheduledJobRun.status == RUN_STATUS_SUCCESS
            )
        ).scalar_one()
    )
    return HealthSummary(
        healthy=len(issues) == 0,
        issues=issues,
        last_tick_at=last_tick,
        failure_streaks=streaks,
    )
