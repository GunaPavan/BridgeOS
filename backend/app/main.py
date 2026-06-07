"""FastAPI application entry point."""

# Load .env into os.environ BEFORE any module reads env vars. The agent's
# LLM client + embeddings client read BEDROCK_REGION / ANTHROPIC_API_KEY /
# etc. directly via os.environ at call time, so we have to populate the
# process environment before they execute. pydantic-settings already loads
# .env for Settings, but only into the Settings instance — not os.environ.
from dotenv import load_dotenv

load_dotenv(override=False)

# Phase E10: pull Secrets Manager values into os.environ NOW, before any
# downstream module (app.db, app.integrations.*) imports and reads env at
# module load time. Must happen here, NOT inside the lifespan handler —
# lifespan runs after engine creation.
import os
if os.environ.get("BRIDGE_OS_USE_SECRETS_MANAGER", "").lower() in ("1", "true", "yes"):
    try:
        from app.integrations.secrets import load_secrets_into_env

        load_secrets_into_env()
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Secrets Manager load failed")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import (
    agent_router,
    analytics_router,
    bridges_router,
    donors_router,
    integrations_router,
    outreach_router,
    patients_router,
    recommendations_router,
    schedule_router,
    simulator_router,
    stability_router,
    whatsapp_router,
)
from app.api.dispatch_queue import router as dispatch_queue_router
from app.api.emails import router as emails_router
from app.api.admin_demo import router as admin_demo_router
from app.api.admin_test import router as admin_test_router
from app.api.auth import router as auth_router
from app.api.donor_portal import router as donor_portal_router
from app.api.events import router as events_router
from app.api.patient_portal import router as patient_portal_router
from app.api.inbound_email import router as inbound_email_router
from app.api.twilio_voice import router as twilio_voice_router
from app.api.ml_predictions import router as ml_predictions_router
from app.api.reply_classifications import router as reply_classifications_router
from app.api.scheduler import router as scheduler_router
from app.api.system import router as system_router
from app.config import get_settings
from app.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Boot + shut down the Automation Engine alongside FastAPI.

    The scheduler reads ``ScheduledJob`` rows at startup so pause/resume
    state survives restarts. Shutdown waits for in-flight jobs only briefly
    (uvicorn's grace period takes over after that).
    """
    # Skip scheduler under pytest — tests spin up the runtime explicitly
    # when they need it. Avoids stray APScheduler threads holding the DB.
    import os
    if os.getenv("BRIDGE_OS_DISABLE_SCHEDULER") != "1":
        try:
            start_scheduler()
        except Exception:  # pragma: no cover — never block API boot on scheduler
            import logging
            logging.getLogger(__name__).exception("Scheduler failed to start")
    try:
        yield
    finally:
        try:
            stop_scheduler()
        except Exception:  # pragma: no cover
            pass


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    app = FastAPI(
        title="Bridge OS API",
        description=(
            "Software infrastructure for scaling Blood Warriors' Blood Bridge model. "
            "Recurring transfusion care for thalassemia patients across India."
        ),
        version=__version__,
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Meta endpoints ---
    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok", "version": __version__}

    @app.get("/", tags=["meta"])
    def root() -> dict[str, str]:
        """API root."""
        return {
            "name": "Bridge OS API",
            "version": __version__,
            "docs": "/docs",
        }

    # --- Feature routers ---
    app.include_router(bridges_router)
    app.include_router(donors_router)
    app.include_router(patients_router)
    app.include_router(stability_router)
    app.include_router(schedule_router)
    app.include_router(recommendations_router)
    app.include_router(analytics_router)
    app.include_router(integrations_router)
    app.include_router(simulator_router)
    app.include_router(whatsapp_router)
    app.include_router(ml_predictions_router)
    app.include_router(system_router)
    app.include_router(agent_router)
    app.include_router(outreach_router)
    app.include_router(scheduler_router)
    app.include_router(reply_classifications_router)
    # Inbound MUST be registered before emails so /emails/inbound doesn't get
    # intercepted by /emails/{id: UUID} → 422
    app.include_router(inbound_email_router)
    app.include_router(emails_router)
    app.include_router(dispatch_queue_router)
    app.include_router(events_router)
    app.include_router(twilio_voice_router)
    app.include_router(auth_router)
    app.include_router(donor_portal_router)
    app.include_router(patient_portal_router)
    app.include_router(admin_test_router)
    app.include_router(admin_demo_router)

    return app


app = create_app()
