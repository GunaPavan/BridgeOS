"""Integration tests for the /donors endpoints."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.fixtures import build_test_dataset, feature_bridge_destabilizer


def _seed(db_session: Session):
    data = build_test_dataset(db_session, n_patients=10, n_donors=100, seed=42)
    db_session.commit()
    return data


def test_list_donors_returns_pagination_envelope(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    response = client.get("/donors")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 100
    assert body["skip"] == 0
    assert body["limit"] == 50
    assert len(body["items"]) == 50
    sample = body["items"][0]
    for field in (
        "id", "name", "age", "blood_group", "rh_negative", "kell_negative",
        "city", "state", "preferred_language",
        "last_donation_date", "days_since_donation", "total_donations",
        "response_rate", "avg_response_hours",
        "is_active", "is_eligible_to_donate", "bridge_count",
    ):
        assert field in sample, f"missing field: {field}"


def test_list_donors_filter_by_blood_group(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    response = client.get("/donors?blood_group=O%2B&limit=200")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] > 0
    for donor in body["items"]:
        assert donor["blood_group"] == "O+"


def test_list_donors_filter_kell_negative(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    response = client.get("/donors?kell_negative=true&limit=200")
    assert response.status_code == 200
    for donor in response.json()["items"]:
        assert donor["kell_negative"] is True


def test_list_donors_filter_is_active(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    inactive = client.get("/donors?is_active=false&limit=200").json()
    active = client.get("/donors?is_active=true&limit=200").json()
    assert inactive["total"] + active["total"] == 100
    for donor in inactive["items"]:
        assert donor["is_active"] is False


def test_list_donors_search_by_name_case_insensitive(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    # Search by a substring known to exist in the fixture (donors named "Donor 001" etc.)
    needle = data.donors[0].name.split()[0].lower()
    response = client.get(f"/donors?search={needle}")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert any(needle in d["name"].lower() for d in body["items"])


def test_list_donors_sort_by_response_rate_desc(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    body = client.get("/donors?sort=response_rate&order=desc&limit=10").json()
    rates = [d["response_rate"] for d in body["items"]]
    assert rates == sorted(rates, reverse=True)


def test_list_donors_rejects_invalid_sort(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    response = client.get("/donors?sort=email")
    assert response.status_code == 400


def test_list_donors_honors_pagination(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    page1 = client.get("/donors?skip=0&limit=10").json()["items"]
    page2 = client.get("/donors?skip=10&limit=10").json()["items"]
    assert len({d["id"] for d in page1 + page2}) == 20


def test_get_donor_detail_includes_bridge_memberships(
    client: TestClient, db_session: Session
) -> None:
    """Detail endpoint shape, exercised via the feature-bridge destabilizer."""
    data = _seed(db_session)
    db_session.commit()
    destab = feature_bridge_destabilizer(data)
    response = client.get(f"/donors/{destab.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == destab.name
    assert "memberships" in body
    assert isinstance(body["memberships"], list)
    assert len(body["memberships"]) >= 1
    membership = body["memberships"][0]
    for field in (
        "membership_id", "bridge_id", "bridge_name", "bridge_status",
        "patient_id", "patient_name", "patient_age", "patient_blood_group",
        "role", "status", "joined_at",
    ):
        assert field in membership, f"missing field in membership: {field}"



def test_get_donor_returns_404_for_unknown_id(client: TestClient) -> None:
    response = client.get(f"/donors/{uuid.uuid4()}")
    assert response.status_code == 404
