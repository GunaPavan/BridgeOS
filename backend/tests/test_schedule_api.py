"""Integration tests for the /bridges/{id}/schedule endpoint."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.fixtures import build_test_dataset, feature_bridge_destabilizer


def _seed(db_session: Session):
    return build_test_dataset(db_session, n_patients=4, n_donors=80, seed=42)



def test_schedule_assigns_only_active_cohort_donors(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge_id = data.feature_patient.bridge.id

    bridge = data.feature_patient.bridge
    cohort_ids = {str(m.donor.id) for m in bridge.memberships}

    body = client.get(f"/bridges/{bridge_id}/schedule").json()
    for slot in body["slots"]:
        assert slot["donor_id"] in cohort_ids


def test_donor_load_sums_to_slot_count(client: TestClient, db_session: Session) -> None:
    data = _seed(db_session)
    db_session.commit()
    body = client.get(f"/bridges/{data.feature_patient.bridge.id}/schedule").json()
    assert sum(d["assignment_count"] for d in body["donor_load"]) == len(body["slots"])


def test_resolve_endpoint_returns_same_shape(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge_id = data.feature_patient.bridge.id

    response = client.post(f"/bridges/{bridge_id}/schedule/resolve")
    assert response.status_code == 200
    body = response.json()
    assert body["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(body["slots"]) > 0


def test_schedule_returns_404_for_unknown_bridge(client: TestClient) -> None:
    response = client.get(f"/bridges/{uuid.uuid4()}/schedule")
    assert response.status_code == 404


def test_schedule_validates_horizon_bounds(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge_id = data.feature_patient.bridge.id
    assert client.get(f"/bridges/{bridge_id}/schedule?horizon_days=10").status_code == 422
    assert client.get(f"/bridges/{bridge_id}/schedule?horizon_days=2000").status_code == 422


