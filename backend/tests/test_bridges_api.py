"""Integration tests for the /bridges endpoints."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.fixtures import build_test_dataset, feature_bridge_destabilizer


def _seed(db_session: Session, n_patients: int = 10, n_donors: int = 100) -> None:
    build_test_dataset(db_session, n_patients=n_patients, n_donors=n_donors, seed=42)
    db_session.commit()


def test_list_bridges_returns_paginated_payload(client: TestClient, db_session: Session) -> None:
    _seed(db_session, n_patients=10)
    response = client.get("/bridges")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 10
    assert body["skip"] == 0
    assert body["limit"] == 50
    assert len(body["items"]) == 10
    sample = body["items"][0]
    for field in (
        "id", "patient_id", "patient_name", "patient_age", "blood_group",
        "city", "state", "active_donor_count", "health",
    ):
        assert field in sample, f"missing field: {field}"


def test_list_bridges_honors_skip_and_limit(client: TestClient, db_session: Session) -> None:
    _seed(db_session, n_patients=12)
    response = client.get("/bridges?skip=5&limit=3")
    assert response.status_code == 200
    body = response.json()
    assert body["skip"] == 5
    assert body["limit"] == 3
    assert len(body["items"]) == 3


def test_list_bridges_rejects_invalid_pagination(client: TestClient) -> None:
    assert client.get("/bridges?limit=0").status_code == 422
    assert client.get("/bridges?limit=999").status_code == 422
    assert client.get("/bridges?skip=-1").status_code == 422


def test_get_bridge_detail_returns_patient_and_members(
    client: TestClient, db_session: Session
) -> None:
    data = build_test_dataset(db_session, n_patients=3, n_donors=60, seed=1)
    db_session.commit()
    aarav_bridge_id = data.feature_patient.bridge.id

    response = client.get(f"/bridges/{aarav_bridge_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["patient_name"]  # feature patient — name varies
    assert isinstance(body["patient_age"], int) and body["patient_age"] >= 0
    assert body["blood_group"] in {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
    assert "patient" in body
    assert body["patient"]["hospital"]  # any non-empty hospital — name varies with dataset
    assert isinstance(body["members"], list)
    assert len(body["members"]) >= 8
    member = body["members"][0]
    assert "donor" in member
    assert "name" in member["donor"]
    assert "blood_group" in member["donor"]


def test_get_bridge_returns_404_for_unknown_id(client: TestClient) -> None:
    response = client.get(f"/bridges/{uuid.uuid4()}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()



def test_list_bridges_filters_by_health(client: TestClient, db_session: Session) -> None:
    _seed(db_session, n_patients=50, n_donors=500)
    all_body = client.get("/bridges?limit=200").json()
    crit_body = client.get("/bridges?health=critical&limit=200").json()
    # critical must be a strict subset of all bridges
    assert crit_body["total"] < all_body["total"]
    assert all(b["health"] == "critical" for b in crit_body["items"])
    # And summing the three health filters must reconcile with total
    sums = sum(
        client.get(f"/bridges?health={h}&limit=200").json()["total"]
        for h in ("stable", "at_risk", "critical")
    )
    assert sums == all_body["total"]


def test_list_bridges_filters_by_status(client: TestClient, db_session: Session) -> None:
    _seed(db_session, n_patients=10)
    body = client.get("/bridges?status=active&limit=200").json()
    assert body["total"] > 0
    assert all(b["status"] == "active" for b in body["items"])


def test_list_bridges_filters_by_city(client: TestClient, db_session: Session) -> None:
    _seed(db_session, n_patients=50, n_donors=500)
    body = client.get("/bridges?city=Hyderabad&limit=200").json()
    assert body["total"] >= 1  # Aarav is in Hyderabad
    assert all(b["city"].lower() == "hyderabad" for b in body["items"])


def test_list_bridges_filters_by_blood_group(client: TestClient, db_session: Session) -> None:
    _seed(db_session, n_patients=50, n_donors=500)
    body = client.get("/bridges?blood_group=B%2B&limit=200").json()
    assert body["total"] >= 1
    assert all(b["blood_group"] == "B+" for b in body["items"])


def test_list_bridges_search_by_patient_name(client: TestClient, db_session: Session) -> None:
    data = build_test_dataset(db_session, n_patients=50, n_donors=500, seed=42)
    db_session.commit()
    body = client.get(f"/bridges?search={data.feature_patient.name.split()[0]}&limit=200").json()
    assert body["total"] >= 1
    assert any(data.feature_patient.name.split()[0] in b["patient_name"] for b in body["items"])


def test_list_bridges_invalid_health_rejected(client: TestClient) -> None:
    assert client.get("/bridges?health=mostly_dead").status_code == 422
