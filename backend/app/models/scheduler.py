"""Scheduler entities — persistent on/off state + audit log of job runs.

These tables back ``app.scheduler``. The runtime is APScheduler in-process,
but we keep the state in the same SQLAlchemy DB so:

  1. Pause/resume survives a process restart.
  2. Every cycle, every reminder, every escalation gets an auditable row in
     ``ScheduledJobRun`` — coordinators (and CloudWatch later) can answer
     "what fired in the last 24 hours and which ones failed?".
  3. EventBridge Scheduler migration is mechanical — the job functions stay
     identical, only the trigger source changes.

Job names are CODE-DEFINED (registered in ``app/scheduler/registry.py``).
The ``ScheduledJob`` table only stores per-name state — never let users
create / delete rows directly. The startup hook upserts the registry into
this table.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import GUID


class ScheduledJob(Base):
    """One row per code-defined job. Tracks whether it's enabled + the last
    time it ran. Cron is normally taken from the registry; ``cron_override``
    lets an operator change cadence without redeploying."""

    __tablename__ = "scheduled_jobs"

    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    cron_override: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        state = "on" if self.enabled else "PAUSED"
        return f"<ScheduledJob {self.name} {state} last={self.last_run_at}>"


class ScheduledJobRun(Base):
    """One row per execution. status=success|failed|skipped (skipped = job
    was disabled at fire time, or quiet-hours blocked the work).

    ``items_processed`` is a free-form integer that means whatever the job
    cares about (waves created, pings sent, etc.). ``payload_json`` carries
    the rest so the UI can render run-specific detail without schema churn.
    """

    __tablename__ = "scheduled_job_runs"
    __table_args__ = (
        Index("ix_scheduled_job_runs_job_started", "job_name", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    job_name: Mapped[str] = mapped_column(
        String(80), ForeignKey("scheduled_jobs.name", ondelete="CASCADE"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="success", index=True)
    items_processed: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ScheduledJobRun {self.job_name} {self.status} "
            f"items={self.items_processed} dur={self.duration_ms}ms>"
        )
