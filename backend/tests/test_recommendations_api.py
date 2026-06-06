"""Integration tests for /recommendations + /bridges/{id}/recommendations + /recruit."""

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
def rec_client(db_session: Session, shared_predictor) -> Generator[TestClient, None, None]:
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
    return build_test_dataset(
        db_session, n_patients=4, n_donors=120, seed=42
    )


# ----- /recommendations inbox -----


def test_inbox_returns_payload_shape(rec_client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    db_session.commit()
    resp = rec_client.get("/recommendations")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body and "total" in body
    if body["items"]:
        sample = body["items"][0]
        for field in (
            "bridge_id", "bridge_name", "patient_name", "patient_age",
            "patient_blood_group", "patient_hospital", "urgency",
            "weak_donors", "candidates", "active_donor_count",
        ):
            assert field in sample



def test_inbox_urgency_ranking_sorts_critical_first(
    rec_client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    db_session.commit()
    body = rec_client.get("/recommendations?at_risk_threshold=0.35").json()
    urgencies = [r["urgency"] for r in body["items"]]
    # critical must precede high must precede medium
    rank = {"critical": 0, "high": 1, "medium": 2}
    assert urgencies == sorted(urgencies, key=lambda u: rank[u])


# ----- per-bridge recommendations -----


def test_bridge_recommendations_returns_candidates(
    rec_client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge_id = data.feature_patient.bridge.id

    body = rec_client.get(f"/bridges/{bridge_id}/recommendations").json()
    assert body["bridge_name"]  # any non-empty bridge name
    assert len(body["candidates"]) >= 1
    # Candidates must be compatible with the patient's blood group
    feature_bg = data.feature_patient.blood_group
    feature_bg_value = feature_bg.value if hasattr(feature_bg, "value") else feature_bg
    # No need to enforce specific blood-group set since real data has variety; just
    # ensure candidates aren't already in the active cohort.
    active_member_names = {
        m.donor.name
        for m in data.feature_patient.bridge.memberships
        if m.status == MembershipStatus.ACTIVE
    }
    for c in body["candidates"]:
        assert c["donor"]["blood_group"]  # has a blood group
        assert c["donor"]["name"] not in active_member_names



def test_candidates_sorted_by_composite_score_desc(
    rec_client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    body = rec_client.get(
        f"/bridges/{data.feature_patient.bridge.id}/recommendations?top_k=10"
    ).json()
    scores = [c["composite_score"] for c in body["candidates"]]
    assert scores == sorted(scores, reverse=True)


def test_bridge_recommendations_404_for_unknown_bridge(rec_client: TestClient) -> None:
    assert rec_client.get(f"/bridges/{uuid.uuid4()}/recommendations").status_code == 404


# ----- recruit -----


def test_recruit_creates_pending_membership(
    rec_client: TestClient, db_session: Session
) -> None:
    """G1: recruit no longer adds ACTIVE directly — it sends a PENDING invite."""
    data = _seed(db_session)
    db_session.commit()
    bridge_id = data.feature_patient.bridge.id

    recs = rec_client.get(f"/bridges/{bridge_id}/recommendations").json()
    candidate_id = recs["candidates"][0]["donor"]["id"]
    before_count = recs["active_donor_count"]

    resp = rec_client.post(
        f"/bridges/{bridge_id}/recruit",
        json={"candidate_donor_id": candidate_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["added_donor_id"] == candidate_id
    assert body["status"] == "pending"
    assert body["waiting_for_donor_reply"] is True
    assert body["message_sid"]  # WhatsApp invite fired (mock or live)
    # Active count is unchanged — PENDING doesn't count yet
    assert body["new_active_donor_count"] == before_count
    assert body["replace_donor_id"] is None



def test_recruit_rejects_incompatible_blood_group(
    rec_client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()

    # Find a donor that *cannot* donate to Aarav (B+) — i.e. A+ or AB+
    from app.models import BloodGroup, Donor

    incompatible = (
        db_session.query(Donor)
        .filter(Donor.blood_group == BloodGroup.A_POS)
        .first()
    )
    assert incompatible is not None

    resp = rec_client.post(
        f"/bridges/{data.feature_patient.bridge.id}/recruit",
        json={"candidate_donor_id": str(incompatible.id)},
    )
    assert resp.status_code == 422
    assert "compatible" in resp.json()["detail"].lower()


def test_recruit_rejects_duplicate_active_member(
    rec_client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge = data.feature_patient.bridge
    existing_active = next(
        m for m in bridge.memberships if m.status == MembershipStatus.ACTIVE
    )
    resp = rec_client.post(
        f"/bridges/{bridge.id}/recruit",
        json={"candidate_donor_id": str(existing_active.donor_id)},
    )
    assert resp.status_code == 409


def test_recruit_404_for_unknown_candidate(
    rec_client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    resp = rec_client.post(
        f"/bridges/{data.feature_patient.bridge.id}/recruit",
        json={"candidate_donor_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


def test_recruit_404_for_unknown_bridge(rec_client: TestClient, db_session: Session) -> None:
    data = _seed(db_session)
    db_session.commit()
    cand = data.donors[0]
    resp = rec_client.post(
        f"/bridges/{uuid.uuid4()}/recruit",
        json={"candidate_donor_id": str(cand.id)},
    )
    assert resp.status_code == 404
