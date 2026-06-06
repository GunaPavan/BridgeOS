"""Tests for /ml/donor-pool-insights — network-wide ML aggregate scoring.

These tests skip cleanly when either of the production models isn't yet
trained, because that endpoint is a downstream consumer of the bake-off
artifacts and we don't retrain inside the unit suite.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ml.churn import load_predictor as load_churn
from app.ml.survival import load_predictor as load_survival
from tests.fixtures import build_test_dataset


@pytest.fixture(scope="module")
def models_loaded() -> bool:
    """Skip the suite cleanly when either model isn't on disk."""
    return load_churn() is not None and load_survival() is not None


def test_pool_insights_returns_503_when_models_missing(client: TestClient) -> None:
    """If no models on disk, endpoint must surface a clear 503 (never crash)."""
    # ml_predictions.py imports them as `load_churn_predictor` /
    # `load_survival_predictor` — patch in the API module's namespace, not
    # the source modules, because the endpoint resolves names locally.
    from app.api import ml_predictions as _ep

    saved_churn = _ep.load_churn_predictor
    saved_surv = _ep.load_survival_predictor
    _ep.load_churn_predictor = lambda: None  # type: ignore[assignment]
    _ep.load_survival_predictor = lambda: None  # type: ignore[assignment]
    try:
        r = client.get("/ml/donor-pool-insights")
        assert r.status_code == 503
        assert "model" in r.json()["detail"].lower()
    finally:
        _ep.load_churn_predictor = saved_churn
        _ep.load_survival_predictor = saved_surv


def test_pool_insights_returns_empty_shape_when_db_empty(
    client: TestClient, models_loaded: bool
) -> None:
    """No donors in the DB → endpoint returns n_scored=0 + zeroed buckets."""
    if not models_loaded:
        pytest.skip("Production models not loaded — run app.ml.churn.bakeoff first.")
    r = client.get("/ml/donor-pool-insights")
    assert r.status_code == 200
    body = r.json()
    assert body["n_scored"] == 0
    assert body["predicted_class_counts"] == {}
    assert body["needs_reminder_count"] == 0
    assert body["stop_calling_count"] == 0
    assert body["high_risk_count"] == 0
    assert body["low_risk_count"] == 0


def test_pool_insights_aggregates_across_donor_pool(
    client: TestClient, db_session: Session, models_loaded: bool
) -> None:
    """End-to-end happy path: seed a small pool, scoring shapes return."""
    if not models_loaded:
        pytest.skip("Production models not loaded — run app.ml.churn.bakeoff first.")

    # Seed a small synthetic pool — these aren't training inputs, just rows
    # the endpoint can score against the prod models.
    build_test_dataset(db_session, n_patients=4, n_donors=40, seed=7)
    db_session.commit()

    r = client.get("/ml/donor-pool-insights")
    assert r.status_code == 200
    body = r.json()

    # Schema: every documented key is present
    expected_keys = {
        "n_scored",
        "predicted_class_counts",
        "p_active_mean",
        "high_risk_count",
        "low_risk_count",
        "survival_365d_median",
        "survival_365d_p25",
        "survival_365d_p75",
        "needs_reminder_count",
        "stop_calling_count",
        "churn_winner",
        "survival_winner",
    }
    assert expected_keys.issubset(body.keys())

    # Sanity: at least some donors were scored
    assert body["n_scored"] > 0
    # Class counts sum to n_scored
    assert sum(body["predicted_class_counts"].values()) == body["n_scored"]
    # Probabilities live in [0,1]
    assert 0.0 <= body["p_active_mean"] <= 1.0
    assert 0.0 <= body["survival_365d_median"] <= 1.0
    assert 0.0 <= body["survival_365d_p25"] <= 1.0
    assert 0.0 <= body["survival_365d_p75"] <= 1.0
    # Quartile ordering
    assert body["survival_365d_p25"] <= body["survival_365d_median"] <= body["survival_365d_p75"]
    # Intervention counts cannot exceed the scored pool
    assert body["needs_reminder_count"] <= body["n_scored"]
    assert body["stop_calling_count"] <= body["n_scored"]
    assert body["high_risk_count"] <= body["n_scored"]
    assert body["low_risk_count"] <= body["n_scored"]
    # Winner labels are populated
    assert isinstance(body["churn_winner"], str) and len(body["churn_winner"]) > 0
    assert isinstance(body["survival_winner"], str) and len(body["survival_winner"]) > 0
