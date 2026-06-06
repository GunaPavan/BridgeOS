"""Integration tests for the /patients endpoints."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.fixtures import build_test_dataset, feature_bridge_destabilizer


def _seed(db_session: Session):
    data = build_test_dataset(db_session, n_patients=10, n_donors=100, seed=42)
    db_session.commit()
    return data


def test_list_patients_returns_pagination_envelope(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    response = client.get("/patients")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 10
    assert body["skip"] == 0
    assert body["limit"] == 50
    assert len(body["items"]) == 10
    sample = body["items"][0]
    for field in (
        "id", "name", "age", "blood_group", "rh_negative", "kell_negative",
        "city", "state", "hospital", "preferred_language",
        "transfusion_cadence_days", "last_transfusion_date",
        "next_transfusion_date", "days_until_transfusion",
        "active", "has_bridge", "bridge_health", "active_donor_count",
    ):
        assert field in sample, f"missing field: {field}"


def test_list_patients_filter_by_blood_group(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    response = client.get("/patients?blood_group=B%2B")
    assert response.status_code == 200
    for patient in response.json()["items"]:
        assert patient["blood_group"] == "B+"



def test_list_patients_sort_by_age_desc(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    body = client.get("/patients?sort=age&order=desc").json()
    ages = [p["age"] for p in body["items"]]
    assert ages == sorted(ages, reverse=True)


def test_list_patients_rejects_invalid_sort(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    assert client.get("/patients?sort=email").status_code == 400


def test_list_patients_filter_has_bridge_true(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    body = client.get("/patients?has_bridge=true&limit=200").json()
    for patient in body["items"]:
        assert patient["has_bridge"] is True
        assert patient["bridge_health"] in {"stable", "at_risk", "critical"}


def test_list_patients_filter_by_bridge_health(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    body = client.get("/patients?bridge_health=stable&limit=200").json()
    for patient in body["items"]:
        assert patient["bridge_health"] == "stable"


def test_get_patient_profile_returns_full_shape(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    feature = data.feature_patient

    response = client.get(f"/patients/{feature.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == feature.name
    assert isinstance(body["age"], int)
    assert body["blood_group"] == feature.blood_group.value if hasattr(feature.blood_group, "value") else feature.blood_group
    for field in (
        "extended_phenotype", "lat", "lng", "registered_at",
        "bridge", "projected_transfusions",
    ):
        assert field in body, f"missing field: {field}"
    assert body["bridge"] is not None
    for f in (
        "bridge_id", "bridge_name", "bridge_status",
        "active_donor_count", "total_donor_count", "health", "created_at",
    ):
        assert f in body["bridge"]



def test_get_patient_returns_404_for_unknown_id(client: TestClient) -> None:
    response = client.get(f"/patients/{uuid.uuid4()}")
    assert response.status_code == 404


def test_list_patients_honors_pagination(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    page1 = client.get("/patients?skip=0&limit=3").json()["items"]
    page2 = client.get("/patients?skip=3&limit=3").json()["items"]
    assert len({p["id"] for p in page1 + page2}) == 6
