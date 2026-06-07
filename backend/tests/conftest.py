"""Pytest fixtures shared across the test suite.

Tests run against an in-memory SQLite database so they're fast and require
no Docker. The ORM uses cross-dialect column types (see `app.models.types.GUID`)
so behavior matches the Postgres production path.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import create_app
from app.models import (  # noqa: F401 (register tables)
    AgentMessage,
    Bridge,
    BridgeMembership,
    CohortMemory,
    Donor,
    DonorResponseEvent,
    EmailMessage,
    Patient,
    ScheduleResolveLog,
    ScheduledJob,
    ScheduledJobRun,
    WhatsAppMessage,
)


# Disable the in-process APScheduler runtime during tests. Each scheduler
# test boots a SchedulerRuntime explicitly against the test DB so we don't
# get stray threads holding the connection pool.
import os
os.environ["BRIDGE_OS_DISABLE_SCHEDULER"] = "1"


@pytest.fixture(autouse=True)
def _isolate_llm_env(monkeypatch):
    """Hide live-LLM env vars so tests start in the deterministic mock/local mode.

    Bridge OS ships with BEDROCK_REGION + AWS creds populated in the developer's
    real environment (and in ``backend/.env``, which the app autoloads at import
    time). Without this fixture, tests like ``test_get_active_provider_defaults_to_local``
    would see the real Bedrock provider and fail. Tests that need a specific
    provider set it explicitly via their own ``monkeypatch.setenv`` — that still
    works because pytest applies fixture-level monkeypatches before test-level ones.
    """
    for var in (
        "BEDROCK_REGION",
        "BEDROCK_SONNET_ID",
        "BEDROCK_HAIKU_ID",
        "BEDROCK_TITAN_ID",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_EMBEDDING_MODEL",
        # Twilio creds — strip so tests run in mock mode regardless of shell
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_WHATSAPP_FROM",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def db_engine():
    """Fresh in-memory SQLite engine per test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    """Fresh session per test."""
    SessionTest = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, future=True)
    session = SessionTest()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """FastAPI test client wired to the test DB session.

    Also bootstraps the scheduler runtime against the test session so the
    scheduler/metrics/demo-mode endpoints respond as they would in prod.
    The standard scheduler lifespan is disabled in tests
    (BRIDGE_OS_DISABLE_SCHEDULER=1) so we have to wire the runtime by hand.
    """
    from app.models import ScheduledJob
    from app.scheduler import REGISTRY
    from app.scheduler.runtime import SchedulerRuntime, _runtime_lock
    import app.scheduler.runtime as rt_mod

    class _NoCloseSession:
        def __init__(self, session: Session) -> None:
            self._session = session

        def __enter__(self) -> Session:
            return self._session

        def __exit__(self, *args) -> None:
            return None

    app = create_app()

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    factory = lambda: _NoCloseSession(db_session)
    with _runtime_lock:
        rt_mod._runtime = SchedulerRuntime(session_factory=factory)
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
        app.dependency_overrides.clear()
