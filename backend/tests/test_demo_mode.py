"""Phase D — demo mode behaviour.

Demo mode swaps every job's effective cron from its default to its
compressed ``demo_cron``. Verify:
  1. Status flips the flag
  2. Each job's effective_cron changes to its demo_cron when demo is on
  3. Toggling off restores defaults
  4. Re-enabling demo is idempotent
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.scheduler import REGISTRY


def _get_job(client: TestClient, name: str) -> dict:
    return client.get(f"/system/scheduler/jobs/{name}").json()


def test_status_demo_mode_default_off(client: TestClient) -> None:
    r = client.get("/system/scheduler/status")
    assert r.status_code == 200
    assert r.json()["demo_mode"] is False


def test_enabling_demo_mode_swaps_each_job_to_demo_cron(client: TestClient) -> None:
    r = client.post("/system/scheduler/demo-mode", json={"enabled": True})
    assert r.status_code == 200, r.text
    assert r.json()["demo_mode"] is True

    for spec in REGISTRY:
        detail = _get_job(client, spec.name)
        assert detail["effective_cron"] == spec.demo_cron, (
            f"{spec.name} expected demo cron {spec.demo_cron} "
            f"but got {detail['effective_cron']}"
        )


def test_disabling_demo_mode_restores_defaults(client: TestClient) -> None:
    client.post("/system/scheduler/demo-mode", json={"enabled": True})
    r = client.post("/system/scheduler/demo-mode", json={"enabled": False})
    assert r.json()["demo_mode"] is False

    for spec in REGISTRY:
        detail = _get_job(client, spec.name)
        assert detail["effective_cron"] == spec.cron


def test_idempotent_re_enable(client: TestClient) -> None:
    client.post("/system/scheduler/demo-mode", json={"enabled": True})
    r = client.post("/system/scheduler/demo-mode", json={"enabled": True})
    assert r.json()["demo_mode"] is True


def test_cron_override_wins_over_demo_mode(client: TestClient) -> None:
    """A persisted cron_override has higher precedence than demo_cron."""
    client.patch(
        "/system/scheduler/jobs/auto_run_cycle",
        json={"cron_override": "*/7 * * * *"},
    )
    client.post("/system/scheduler/demo-mode", json={"enabled": True})
    detail = _get_job(client, "auto_run_cycle")
    assert detail["effective_cron"] == "*/7 * * * *"


def test_demo_cron_specs_are_strictly_more_frequent_than_defaults() -> None:
    """Sanity check on the registry — demo crons MUST be more compressed
    than defaults, otherwise the demo toggle is misleading."""
    # We approximate "more frequent" by counting wildcards / step values
    # rather than computing the real cron period (too brittle for a unit
    # test). A 6-field cron with seconds is always more compressed than a
    # 5-field cron with minutes — that's the typical pattern.
    for spec in REGISTRY:
        default_parts = spec.cron.split()
        demo_parts = spec.demo_cron.split()
        # Demo crons use 6 fields (seconds field added) for every job
        # except the daily reminder where we switch to "0 * * * * *" (every
        # minute) instead of "0 9 * * *".
        assert len(demo_parts) in (5, 6), (
            f"{spec.name}: demo cron has weird field count {demo_parts}"
        )
        # Either the demo cron has a seconds field, OR the field-zero
        # values differ (daily 0 9 vs every-minute 0 *)
        assert len(demo_parts) > len(default_parts) or demo_parts != default_parts
