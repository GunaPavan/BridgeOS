"""Pydantic schemas for the /system/scheduler/* API surface."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


class JobState(BaseModel):
    name: str
    description: str
    enabled: bool
    cron_default: str
    cron_demo: str
    cron_override: Optional[str] = None
    effective_cron: str
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None


class JobUpdateRequest(BaseModel):
    """PATCH /jobs/{name} body. Only updatable field for now is the override.
    Passing ``cron_override=None`` clears the override (back to default)."""

    cron_override: Optional[str] = Field(
        default=None, description="Cron string. Null to clear."
    )
    clear_override: bool = Field(
        default=False,
        description=(
            "Set to true to remove the override. (Pydantic can't distinguish "
            "'field absent' from 'field = null' in JSON, so callers must opt "
            "into clearing explicitly.)"
        ),
    )


class JobDetail(JobState):
    recent_runs: list["RunSummary"] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


class RunSummary(BaseModel):
    id: uuid.UUID
    job_name: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    status: str
    items_processed: int
    error_message: Optional[str] = None


class RunDetail(RunSummary):
    payload: Optional[dict[str, Any]] = None


class RunsPage(BaseModel):
    items: list[RunSummary]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Status + metrics
# ---------------------------------------------------------------------------


class SchedulerStatus(BaseModel):
    running: bool
    demo_mode: bool
    job_count: int
    enabled_count: int
    last_tick_at: Optional[datetime] = None
    failures_24h: int
    jobs: list[JobState]


class DemoModeRequest(BaseModel):
    enabled: bool


class TriggerResult(BaseModel):
    job_name: str
    triggered: bool
    detail: Optional[str] = None


class PruneResult(BaseModel):
    deleted: int


class JobMetric(BaseModel):
    job_name: str
    success: int = 0
    failed: int = 0
    skipped: int = 0
    items_processed_total: int = 0
    avg_duration_ms: Optional[float] = None
    p50_duration_ms: Optional[float] = None
    p95_duration_ms: Optional[float] = None


class SchedulerMetrics(BaseModel):
    window_hours: int
    overall: dict[str, int]
    by_job: list[JobMetric]


class HealthSummary(BaseModel):
    healthy: bool
    issues: list[str]
    last_tick_at: Optional[datetime] = None
    failure_streaks: dict[str, int]


JobDetail.model_rebuild()
