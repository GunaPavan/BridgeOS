"""System-level metadata endpoints (clock anchor, full health, etc.)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.system_clock import system_clock_info


router = APIRouter(prefix="/system", tags=["system"])


@router.get("/clock", summary="System clock + dataset anchor")
def get_system_clock(db: Session = Depends(get_db)) -> dict:
    """Return the dataset-anchored 'today' the system uses for all
    time-since/time-until calculations. The Blood Warriors dataset is a
    snapshot; wall-clock 'now' would render every transfusion as ~250 days
    overdue. Anchoring keeps numbers meaningful."""
    return system_clock_info(db)


# ---------------------------------------------------------------------------
# Phase D — extended health: scheduler, deps, last cycle age
# ---------------------------------------------------------------------------


def _check_db(db: Session) -> tuple[bool, str | None]:
    try:
        db.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # pragma: no cover
        return False, str(exc)[:120]


def _check_scheduler(db: Session) -> dict:
    from app.models import ScheduledJobRun
    from app.scheduler import get_scheduler
    from app.scheduler.metrics import RUN_STATUS_SUCCESS

    runtime = get_scheduler()
    running = bool(runtime and runtime._scheduler.running)
    demo_mode = bool(runtime and runtime.demo_mode)

    last_success_at = db.execute(
        select(ScheduledJobRun.finished_at)
        .where(ScheduledJobRun.status == RUN_STATUS_SUCCESS)
        .order_by(ScheduledJobRun.finished_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    last_cycle_age_seconds = None
    if last_success_at is not None:
        last_cycle_age_seconds = int(
            max(0, (datetime.utcnow() - last_success_at).total_seconds())
        )

    return {
        "running": running,
        "demo_mode": demo_mode,
        "last_success_at": (
            last_success_at.isoformat() + "Z" if last_success_at else None
        ),
        "last_cycle_age_seconds": last_cycle_age_seconds,
    }


def _check_bedrock() -> dict:
    """Bedrock is "reachable" when (a) the env is configured and (b) the
    classifier service thinks it can call it. We DO NOT actually hit the API
    in this endpoint — that would make /health flaky + expensive. We just
    report config status."""
    from app.services.reply_classifier import _bedrock_available

    configured = _bedrock_available()
    return {
        "configured": configured,
        "region": os.environ.get("BEDROCK_REGION") or os.environ.get("AWS_REGION") or None,
        "haiku_id": os.environ.get("BEDROCK_HAIKU_ID") or None,
        "note": None if configured else "BEDROCK_REGION / AWS creds not set — classifier falls back to keyword parser",
    }


def _check_twilio() -> dict:
    from app.integrations.twilio_client import is_live, whatsapp_from

    live = is_live()
    return {
        "configured": live,
        "from_number": whatsapp_from(),
        "mode": "live" if live else "mock",
    }


@router.get(
    "/health/full",
    summary="Full health snapshot — scheduler, DB, Bedrock, Twilio + last cycle age",
)
def get_full_health(db: Session = Depends(get_db)) -> dict:
    """Aggregated dependency health for the dashboard banner.

    The bare ``/health`` endpoint stays cheap (no DB call) for uvicorn /
    App Runner liveness probes. This endpoint adds:
      - DB ping
      - Scheduler running + last successful cycle age
      - Bedrock configured (no actual API call — too expensive for a probe)
      - Twilio configured (mock vs live)

    Returns an overall ``healthy`` boolean that's True iff every required
    dependency is OK. Bedrock + Twilio failing falls back to keyword /
    mock mode respectively, so we don't fail overall health for them —
    they're flagged as warnings instead.
    """
    db_ok, db_err = _check_db(db)
    scheduler = _check_scheduler(db)
    bedrock = _check_bedrock()
    twilio = _check_twilio()
    # Phase E1: report SES/SQS/SNS via the unified probe. We DO NOT call AWS
    # — just report config. Live checks happen at use time.
    from app.integrations.aws import aws_available, friendly_status, resource_prefix

    ses_status = friendly_status("ses")
    sqs_status = friendly_status(
        "sqs", resource=f"{resource_prefix()}-dispatch"
    )
    sns_status = friendly_status(
        "sns", resource=f"{resource_prefix()}-events"
    )
    # E6: SMS via SNS direct-publish (different path from event topics)
    from app.integrations import sns_sms_client
    sms_status = sns_sms_client.friendly_status()

    warnings = []
    if not bedrock["configured"]:
        warnings.append("bedrock: not configured (keyword fallback active)")
    if not twilio["configured"]:
        warnings.append("twilio: not configured (mock sends)")
    if not aws_available():
        warnings.append("aws: no creds — SES/SQS/SNS in mock mode")
    if scheduler["running"] and (
        scheduler["last_cycle_age_seconds"] is not None
        and scheduler["last_cycle_age_seconds"] > 600
    ):
        warnings.append(
            f"scheduler: last successful cycle was "
            f"{scheduler['last_cycle_age_seconds']}s ago (>10 min)"
        )

    healthy = db_ok and scheduler["running"]
    return {
        "healthy": healthy,
        "warnings": warnings,
        "db": {"ok": db_ok, "error": db_err},
        "scheduler": scheduler,
        "bedrock": bedrock,
        "twilio": twilio,
        "ses": ses_status,
        "sqs": sqs_status,
        "sns": sns_status,
        "sms": sms_status,
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }
