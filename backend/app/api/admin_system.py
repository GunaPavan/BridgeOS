"""One-shot system endpoints to populate the production database.

Only used for first-time deployment of a fresh RDS instance. The endpoints
are gated by the same ``X-Admin-Test-Secret`` header as /admin/test/* and
/admin/demo/* so an unauthenticated visitor can't drop the prod DB.

POST /admin/system/seed-from-dataset
    Runs the Blood Warriors CSV ingestion against the live DB. With
    ``reset=true`` (default for first boot), drops + recreates the schema
    first so leftover placeholder rows don't get mixed with the real data.
    Returns the IngestReport so the operator sees how many patients /
    donors / bridges / memberships landed.

GET /admin/system/data-counts
    Sanity check after deployment — returns row counts for the main tables
    so the operator can spot at a glance whether the seed actually ran.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.admin_test import _check_test_secret
from app.db import SessionLocal, get_db
from app.models import (
    Bridge,
    BridgeMembership,
    Donor,
    OutreachPing,
    OutreachWave,
    Patient,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/system", tags=["admin-system"])


# ---------------------------------------------------------------------------
# /seed-from-dataset
# ---------------------------------------------------------------------------


class SeedReport(BaseModel):
    """Mirrors scripts.ingest_real_dataset.IngestReport for the API surface."""

    patients_loaded: int
    donors_loaded: int
    bridges_created: int
    memberships_loaded: int
    rows_skipped: int
    errors: list[str]
    duration_seconds: float
    source_path: str
    reset_schema: bool
    feature_patient_id: Optional[str] = None


def _resolve_dataset_path() -> Path:
    """The Dockerfile copies ``backend/data/`` into ``/app/data/``. Local dev
    keeps the same layout. Either way the CSV lives at ``data/Dataset.csv``
    relative to the working directory the uvicorn process runs from."""
    here = Path(__file__).resolve()
    # app/api/admin_system.py → app/ → backend/ → data/Dataset.csv
    candidates = [
        here.parent.parent.parent / "data" / "Dataset.csv",  # backend/data/...
        Path.cwd() / "data" / "Dataset.csv",                 # cwd fallback
        Path("/app/data/Dataset.csv"),                       # Docker absolute
    ]
    for p in candidates:
        if p.exists():
            return p
    raise HTTPException(
        status_code=500,
        detail=(
            "Dataset.csv not found in any of: "
            + ", ".join(str(p) for p in candidates)
        ),
    )


@router.post(
    "/seed-from-dataset",
    response_model=SeedReport,
    summary=(
        "First-boot seed: drop + recreate schema, then ingest Blood Warriors "
        "Dataset.csv. Idempotent re-run safe (uses natural keys)."
    ),
)
def seed_from_dataset(
    reset: bool = Query(
        True,
        description=(
            "Drop + recreate the entire schema before ingest. Default true so "
            "leftover placeholder rows from a fresh RDS don't pollute the seed."
        ),
    ),
    _guard: None = Depends(_check_test_secret),
) -> SeedReport:
    from scripts.ingest_real_dataset import ingest_real_dataset

    dataset_path = _resolve_dataset_path()
    logger.info(
        "seed-from-dataset triggered (reset=%s, path=%s)", reset, dataset_path
    )

    # Open the session inside the handler so the ingest doesn't keep a
    # connection pinned across the long-running transaction.
    with SessionLocal() as db:
        try:
            report = ingest_real_dataset(
                db,
                source_path=str(dataset_path),
                fmt="csv",
                reset_schema=reset,
            )
        except Exception as exc:  # pragma: no cover — surface root cause to caller
            logger.exception("seed-from-dataset failed")
            raise HTTPException(status_code=500, detail=f"ingest failed: {exc}") from exc

    duration = (
        (report.finished_at - report.started_at).total_seconds()
        if report.finished_at
        else 0.0
    )
    logger.info("seed-from-dataset finished: %s", report.summary())
    return SeedReport(
        patients_loaded=report.patients_loaded,
        donors_loaded=report.donors_loaded,
        bridges_created=report.bridges_created,
        memberships_loaded=report.memberships_loaded,
        rows_skipped=report.rows_skipped,
        errors=report.errors[:50],  # cap so we don't blow up the response
        duration_seconds=duration,
        source_path=str(dataset_path),
        reset_schema=reset,
        feature_patient_id=report.feature_patient_id,
    )


# ---------------------------------------------------------------------------
# /data-counts — open read so anyone (judges, monitoring) can sanity check
# ---------------------------------------------------------------------------


class DataCounts(BaseModel):
    patients: int
    donors: int
    bridges: int
    memberships: int
    waves: int
    pings: int


@router.get(
    "/data-counts",
    response_model=DataCounts,
    summary="Row counts on the main tables — proves the seed ran in prod.",
)
def data_counts(db: Session = Depends(get_db)) -> DataCounts:
    def _count(model) -> int:
        return int(db.execute(select(func.count()).select_from(model)).scalar() or 0)

    return DataCounts(
        patients=_count(Patient),
        donors=_count(Donor),
        bridges=_count(Bridge),
        memberships=_count(BridgeMembership),
        waves=_count(OutreachWave),
        pings=_count(OutreachPing),
    )
