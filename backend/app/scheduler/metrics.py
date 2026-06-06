"""Run accounting — every job execution becomes a ScheduledJobRun row.

Pure JobResult dataclass so handlers don't import the DB layer. The runtime
wraps each call, captures the result + any exception, and writes the audit
row.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from sqlalchemy.orm import Session

from app.models import ScheduledJobRun

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status sentinels
# ---------------------------------------------------------------------------

RUN_STATUS_SUCCESS = "success"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_SKIPPED = "skipped"


@dataclass
class JobResult:
    """What every job handler returns.

    ``items_processed`` is intentionally generic — the allocator job counts
    waves created; the pending-nudge job counts nudges sent. The number is
    only used for human-readable summaries (and an "any work?" check).

    ``payload`` is a free-form dict that the run record JSON-encodes. The
    UI uses it to render job-specific detail without forcing the schema to
    track every field per job type.
    """

    items_processed: int = 0
    payload: dict[str, Any] = field(default_factory=dict)
    skipped_reason: Optional[str] = None  # set to mark a SKIPPED run

    @property
    def is_skipped(self) -> bool:
        return self.skipped_reason is not None


# ---------------------------------------------------------------------------
# Run accounting
# ---------------------------------------------------------------------------


@contextmanager
def record_run(db: Session, *, job_name: str) -> Iterator["RunContext"]:
    """Context manager that wraps a job execution and writes the audit row.

    Usage::

        with record_run(db, job_name="auto_run_cycle") as ctx:
            result = handler(db=db, now=ctx.started_at)
            ctx.set_result(result)

    On any exception inside the ``with`` block, the run is recorded with
    status=FAILED and the exception message is captured. The exception is
    re-raised so the runtime can see it (and log it) — but the audit row
    is committed first so we never lose the failure trail.
    """
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    ctx = RunContext(job_name=job_name, started_at=started_at)

    try:
        yield ctx
    except Exception as exc:  # pragma: no cover — exercised by integration tests
        ctx._error_message = str(exc) or exc.__class__.__name__
        ctx._status = RUN_STATUS_FAILED
        logger.exception("Scheduled job %s failed", job_name)
        _persist(db, ctx)
        raise

    _persist(db, ctx)


def _persist(db: Session, ctx: "RunContext") -> None:
    finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
    duration_ms = (finished_at - ctx.started_at).total_seconds() * 1000.0

    row = ScheduledJobRun(
        job_name=ctx.job_name,
        started_at=ctx.started_at,
        finished_at=finished_at,
        duration_ms=round(duration_ms, 3),
        status=ctx._status,
        items_processed=ctx._items_processed,
        error_message=ctx._error_message,
        payload_json=(
            json.dumps(ctx._payload, default=str) if ctx._payload else None
        ),
    )
    db.add(row)
    # Touch the parent ScheduledJob.last_run_at so the API can answer
    # "when did this last fire" without scanning the audit table.
    from app.models import ScheduledJob

    job = db.get(ScheduledJob, ctx.job_name)
    if job is not None:
        job.last_run_at = finished_at
    db.commit()


@dataclass
class RunContext:
    """Mutable accumulator used by the ``record_run`` context manager."""

    job_name: str
    started_at: datetime
    _status: str = RUN_STATUS_SUCCESS
    _items_processed: int = 0
    _error_message: Optional[str] = None
    _payload: dict[str, Any] = field(default_factory=dict)

    def set_result(self, result: JobResult) -> None:
        if result.is_skipped:
            self._status = RUN_STATUS_SKIPPED
            self._payload = {"skipped_reason": result.skipped_reason, **result.payload}
        else:
            self._status = RUN_STATUS_SUCCESS
            self._payload = dict(result.payload)
        self._items_processed = int(result.items_processed)
