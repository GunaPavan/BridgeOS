"""Automation Engine — background scheduler that runs the allocator,
expires waves, sends follow-ups, and handles donor-reply side effects
without an operator clicking anything.

Public surface:
    start_scheduler(app, db_url)      — call from FastAPI lifespan
    stop_scheduler()                  — call from FastAPI shutdown
    get_scheduler()                   — current SchedulerRuntime singleton
    REGISTRY                          — declarative job catalogue
    JobResult                         — return type all job handlers produce

The runtime is APScheduler in-process for the demo. The job handlers are
pure ``(db: Session, now: datetime) -> JobResult`` functions so the same
code runs unchanged when we migrate to EventBridge Scheduler + Lambda.
"""

from app.scheduler.registry import REGISTRY, JobSpec
from app.scheduler.runtime import (
    SchedulerRuntime,
    get_scheduler,
    start_scheduler,
    stop_scheduler,
)
from app.scheduler.metrics import JobResult, record_run

__all__ = [
    "REGISTRY",
    "JobSpec",
    "SchedulerRuntime",
    "JobResult",
    "get_scheduler",
    "start_scheduler",
    "stop_scheduler",
    "record_run",
]
