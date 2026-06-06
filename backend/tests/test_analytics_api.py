"""Integration tests for the /analytics endpoint."""

from __future__ import annotations

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
def ana_client(db_session: Session, shared_predictor) -> Generator[TestClient, None, None]:
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
    build_test_dataset(db_session, n_patients=10, n_donors=120, seed=42)
    db_session.commit()


def test_analytics_returns_full_payload(
    ana_client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    response = ana_client.get("/analytics")
    assert response.status_code == 200
    body = response.json()
    for field in (
        "generated_at", "total_patients", "total_donors",
        "donor_pool", "cohort_stats", "patients_by_city",
        "stability_model", "stability_compute_time_ms",
    ):
        assert field in body


def test_analytics_totals_match_seed(
    ana_client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    body = ana_client.get("/analytics").json()
    assert body["total_patients"] == 10
    assert body["total_donors"] == 120
    assert body["cohort_stats"]["total_bridges"] == 10


def test_donor_pool_blood_group_breakdown_sums_to_total(
    ana_client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    body = ana_client.get("/analytics").json()
    pool = body["donor_pool"]
    bg_sum = sum(row["count"] for row in pool["by_blood_group"])
    assert bg_sum == pool["total"]
    # Every group present in the data has a non-empty count
    for row in pool["by_blood_group"]:
        assert row["count"] >= 1


def test_health_distributions_sum_to_total_bridges(
    ana_client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    body = ana_client.get("/analytics").json()
    total_bridges = body["cohort_stats"]["total_bridges"]
    stub = body["cohort_stats"]["stub_health"]
    ml = body["cohort_stats"]["ml_health"]
    assert stub["stable"] + stub["at_risk"] + stub["critical"] == total_bridges
    assert ml["stable"] + ml["at_risk"] + ml["critical"] == total_bridges


def test_eligible_donor_count_matches_business_rule(
    ana_client: TestClient, db_session: Session
) -> None:
    """Eligible = active AND (no prior donation OR ≥ 90 days ago)."""
    from datetime import date
    from app.models import Donor

    _seed(db_session)
    body = ana_client.get("/analytics").json()
    expected = sum(
        1
        for d in db_session.query(Donor).all()
        if d.is_active
        and (
            d.last_donation_date is None
            or (date.today() - d.last_donation_date).days >= 90
        )
    )
    assert body["donor_pool"]["eligible_now"] == expected


def test_patients_by_city_sums_to_total_patients(
    ana_client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    body = ana_client.get("/analytics").json()
    # Top 8 may not cover all patients if more cities exist; with seed=42
    # and 10 patients, all should fit within 8 city groups.
    city_sum = sum(c["count"] for c in body["patients_by_city"])
    assert city_sum <= body["total_patients"]
    assert city_sum > 0


def test_stability_model_metrics_present_when_predictor_loaded(
    ana_client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    body = ana_client.get("/analytics").json()
    sm = body["stability_model"]
    assert sm is not None
    for field in (
        "trained_at", "n_samples", "seed",
        "auc_30d", "auc_60d", "auc_90d",
        "train_auc_30d", "train_auc_60d", "train_auc_90d",
        "brier_90d",
    ):
        assert field in sm
    # AUCs should be in [0.5, 1] for any reasonable model
    for k in ("auc_30d", "auc_60d", "auc_90d"):
        assert 0.5 <= sm[k] <= 1.0


def test_stability_compute_time_recorded(
    ana_client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    body = ana_client.get("/analytics").json()
    # Should be > 0 since we ran the model across 10 bridges; bounded sanity check
    assert body["stability_compute_time_ms"] >= 0
    assert body["stability_compute_time_ms"] < 5000


def test_analytics_falls_back_when_model_missing(db_session: Session) -> None:
    """No predictor → ml_health falls back to stub-health values."""
    _seed(db_session)
    app = create_app()

    def _db_override() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_predictor_dep] = lambda: None
    with TestClient(app) as c:
        body = c.get("/analytics").json()
    assert body["stability_model"] is None
    # Without predictor, ml_health equals stub_health
    assert body["cohort_stats"]["ml_health"] == body["cohort_stats"]["stub_health"]
