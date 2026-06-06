"""Integration tests for the /simulator endpoint."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.stability import get_predictor_dep
from app.db import get_db
from app.main import create_app
from app.ml.stability import StabilityPredictor
from app.ml.stability import get_predictor as _load_real_predictor
from app.models import MembershipStatus
from tests.fixtures import build_test_dataset, feature_bridge_destabilizer


@pytest.fixture(scope="module")
def shared_predictor():
    """Load the real-data trained churn predictor from disk.

    The synthetic-trained model is gone; this returns the production
    StabilityPredictor that adapts the new ChurnPredictor under the hood.
    Tests that need this fixture must be run after `python -m app.ml.churn.bakeoff`."""
    predictor = _load_real_predictor()
    if predictor is None:
        import pytest
        pytest.skip("Churn model artifact not found — run app.ml.churn.bakeoff first.")
    return predictor
@pytest.fixture
def sim_client(db_session: Session, shared_predictor) -> Generator[TestClient, None, None]:
    app = create_app()

    def _db_override() -> Generator[Session, None, None]:
        yield db_session

    def _predictor_override() -> StabilityPredictor:
        return shared_predictor

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_predictor_dep] = _predictor_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db_session: Session):
    return build_test_dataset(db_session, n_patients=4, n_donors=80, seed=42)


# ----- shape -----


def test_baseline_run_with_no_ejections(sim_client: TestClient, db_session: Session) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge_id = data.feature_patient.bridge.id

    resp = sim_client.post(f"/simulator/bridges/{bridge_id}/scenario", json={})
    assert resp.status_code == 200
    body = resp.json()
    for field in ("bridge_id", "bridge_name", "today", "requested", "baseline", "scenario", "delta"):
        assert field in body
    assert body["baseline"]["active_donor_count"] == body["scenario"]["active_donor_count"]
    assert body["delta"]["cohort_size_change"] == 0


def test_ejecting_one_donor_shrinks_cohort(sim_client: TestClient, db_session: Session) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge = data.feature_patient.bridge
    bridge_id = bridge.id
    active_ids = [
        str(m.donor_id) for m in bridge.memberships if m.status == MembershipStatus.ACTIVE
    ]
    eject_id = active_ids[0]

    body = sim_client.post(
        f"/simulator/bridges/{bridge_id}/scenario",
        json={"ejected_donor_ids": [eject_id]},
    ).json()
    assert body["scenario"]["active_donor_count"] == body["baseline"]["active_donor_count"] - 1
    assert body["delta"]["cohort_size_change"] == -1
    # The ejected donor must NOT be in the post-action cohort
    scenario_donor_ids = {m["donor_id"] for m in body["scenario"]["cohort"]}
    assert eject_id not in scenario_donor_ids


def test_ejection_does_not_mutate_database(
    sim_client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge = data.feature_patient.bridge
    bridge_id = bridge.id
    active_before = sum(
        1 for m in bridge.memberships if m.status == MembershipStatus.ACTIVE
    )
    eject_id = str(
        next(m for m in bridge.memberships if m.status == MembershipStatus.ACTIVE).donor_id
    )

    sim_client.post(
        f"/simulator/bridges/{bridge_id}/scenario",
        json={"ejected_donor_ids": [eject_id]},
    )
    db_session.refresh(bridge)
    active_after = sum(
        1 for m in bridge.memberships if m.status == MembershipStatus.ACTIVE
    )
    assert active_after == active_before



def test_scenario_surfaces_replacement_candidates(
    sim_client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge = data.feature_patient.bridge
    eject_id = str(
        next(m for m in bridge.memberships if m.status == MembershipStatus.ACTIVE).donor_id
    )
    body = sim_client.post(
        f"/simulator/bridges/{bridge.id}/scenario",
        json={"ejected_donor_ids": [eject_id]},
    ).json()
    # After ejection the candidate pool should include at least one replacement
    assert len(body["scenario"]["top_candidates"]) >= 1
    sample = body["scenario"]["top_candidates"][0]
    for field in ("donor", "composite_score", "distance_km", "predicted_churn_90d"):
        assert field in sample


def test_scenario_schedule_resolves_after_ejection(
    sim_client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge = data.feature_patient.bridge
    eject_id = str(
        next(m for m in bridge.memberships if m.status == MembershipStatus.ACTIVE).donor_id
    )
    body = sim_client.post(
        f"/simulator/bridges/{bridge.id}/scenario",
        json={"ejected_donor_ids": [eject_id]},
    ).json()
    assert body["scenario"]["schedule_status"] in {"OPTIMAL", "FEASIBLE", "INFEASIBLE"}
    assert body["scenario"]["schedule_solve_time_ms"] >= 0


def test_unknown_bridge_returns_404(sim_client: TestClient) -> None:
    resp = sim_client.post(
        f"/simulator/bridges/{uuid.uuid4()}/scenario", json={"ejected_donor_ids": []}
    )
    assert resp.status_code == 404


def test_scenario_returns_503_when_model_missing(db_session: Session) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge_id = data.feature_patient.bridge.id
    app = create_app()
    app.dependency_overrides[get_db] = lambda: iter([db_session])
    app.dependency_overrides[get_predictor_dep] = lambda: None
    with TestClient(app) as c:
        resp = c.post(f"/simulator/bridges/{bridge_id}/scenario", json={})
    assert resp.status_code == 503
