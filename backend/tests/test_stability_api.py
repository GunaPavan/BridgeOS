"""Integration tests for the /bridges/{id}/stability endpoint."""

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
def ml_client(db_session: Session, shared_predictor) -> Generator[TestClient, None, None]:
    """Test client with an overridden stability predictor available."""
    app = create_app()

    def _db_override():
        yield db_session

    def _predictor_override():
        return shared_predictor

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_predictor_dep] = _predictor_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db_session: Session):
    return build_test_dataset(
        db_session, n_patients=4, n_donors=80, seed=42
    )


def test_stability_endpoint_returns_per_donor_predictions(
    ml_client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge_id = data.feature_patient.bridge.id

    response = ml_client.get(f"/bridges/{bridge_id}/stability")
    assert response.status_code == 200
    body = response.json()

    for field in ("bridge_id", "bridge_name", "computed_at", "model_version", "aggregate", "members"):
        assert field in body
    assert body["model_version"] == "stability_v1"
    assert len(body["members"]) >= 1


def test_stability_aggregate_health_is_valid_bucket(
    ml_client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge_id = data.feature_patient.bridge.id

    body = ml_client.get(f"/bridges/{bridge_id}/stability").json()
    agg = body["aggregate"]
    assert agg["ml_health"] in {"stable", "at_risk", "critical"}
    assert 0.0 <= agg["avg_churn_90d"] <= 1.0
    assert 0.0 <= agg["max_churn_90d"] <= 1.0
    assert agg["max_churn_90d"] >= agg["avg_churn_90d"]




def test_stability_members_include_shap_factors(
    ml_client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge_id = data.feature_patient.bridge.id

    body = ml_client.get(f"/bridges/{bridge_id}/stability").json()
    sample = body["members"][0]
    for field in ("donor_id", "donor_name", "churn_30d", "churn_60d", "churn_90d", "top_factors"):
        assert field in sample
    assert isinstance(sample["top_factors"], list)
    assert len(sample["top_factors"]) >= 1
    factor = sample["top_factors"][0]
    for field in ("feature", "label", "direction", "impact"):
        assert field in factor
    assert factor["direction"] in {"increases_churn", "decreases_churn"}


def test_stability_returns_503_when_model_missing(db_session: Session) -> None:
    """If the predictor isn't loaded, the endpoint must surface 503."""
    data = _seed(db_session)
    db_session.commit()
    bridge_id = data.feature_patient.bridge.id

    app = create_app()
    app.dependency_overrides[get_db] = lambda: iter([db_session])
    app.dependency_overrides[get_predictor_dep] = lambda: None
    with TestClient(app) as c:
        response = c.get(f"/bridges/{bridge_id}/stability")
    assert response.status_code == 503
    assert "train_stability" in response.json()["detail"]


def test_stability_returns_404_for_unknown_bridge(ml_client: TestClient) -> None:
    response = ml_client.get(f"/bridges/{uuid.uuid4()}/stability")
    assert response.status_code == 404
