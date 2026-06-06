"""Integration tests for the /integrations endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


# ----- GET /integrations -----


def test_integrations_status_lists_all_four(client: TestClient) -> None:
    body = client.get("/integrations").json()
    assert "items" in body
    assert "generated_at" in body
    keys = {item["key"] for item in body["items"]}
    # Bedrock replaced Azure OpenAI as the LLM provider for the care agent.
    assert keys == {"eraktkosh", "icmr_rdri", "whatsapp_business", "aws_bedrock"}


def test_eraktkosh_and_icmr_are_mocked_others_unconfigured(
    client: TestClient, monkeypatch
) -> None:
    # Force Bedrock off so the test sees the unconfigured baseline.
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    body = client.get("/integrations").json()
    by_key = {item["key"]: item for item in body["items"]}
    assert by_key["eraktkosh"]["status"] == "mocked"
    assert by_key["icmr_rdri"]["status"] == "mocked"
    assert by_key["whatsapp_business"]["status"] == "not_configured"
    assert by_key["aws_bedrock"]["status"] == "not_configured"


def test_aws_bedrock_flips_to_connected_when_region_is_set(
    client: TestClient, monkeypatch
) -> None:
    """The Bedrock card reflects live env state — coordinators see at a glance
    whether the multi-model AI layer is active."""
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    body = client.get("/integrations").json()
    by_key = {item["key"]: item for item in body["items"]}
    assert by_key["aws_bedrock"]["status"] == "connected"
    assert by_key["aws_bedrock"]["last_sync"] is not None


def test_mocked_integrations_expose_sample_counts(client: TestClient) -> None:
    body = client.get("/integrations").json()
    by_key = {item["key"]: item for item in body["items"]}
    assert by_key["eraktkosh"]["sample_count"] >= 8
    assert by_key["icmr_rdri"]["sample_count"] >= 5


def test_integration_status_includes_phase_and_docs(client: TestClient) -> None:
    body = client.get("/integrations").json()
    for item in body["items"]:
        # phase is a non-empty label (Phase 8 / Phase 10 / Care Agent etc.)
        assert isinstance(item["phase"], str) and item["phase"]
        assert item["docs_url"] is not None


# ----- GET /integrations/eraktkosh/inventory -----


def test_eraktkosh_inventory_returns_blood_banks(client: TestClient) -> None:
    body = client.get("/integrations/eraktkosh/inventory").json()
    assert body["source"] == "eraktkosh"
    assert body["status"] == "mocked"
    assert len(body["blood_banks"]) >= 8
    sample = body["blood_banks"][0]
    for field in ("name", "city", "state", "lat", "lng", "phone", "inventory", "last_updated"):
        assert field in sample
    # Inventory has all 8 standard ABO+Rh groups
    assert set(sample["inventory"].keys()) == {
        "O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"
    }


def test_eraktkosh_city_filter_restricts_results(client: TestClient) -> None:
    body = client.get("/integrations/eraktkosh/inventory?city=Hyderabad").json()
    assert body["city_filter"] == "Hyderabad"
    assert len(body["blood_banks"]) >= 1
    for bank in body["blood_banks"]:
        assert bank["city"].lower() == "hyderabad"


def test_eraktkosh_blood_group_filter_only_includes_centres_with_stock(
    client: TestClient,
) -> None:
    body = client.get(
        "/integrations/eraktkosh/inventory?blood_group=B%2B"
    ).json()
    assert body["blood_group_filter"] == "B+"
    for bank in body["blood_banks"]:
        assert bank["inventory"]["B+"] > 0


def test_eraktkosh_inventory_is_deterministic_within_a_day(
    client: TestClient,
) -> None:
    """Calling twice for the same city + day returns the same inventory."""
    a = client.get("/integrations/eraktkosh/inventory?city=Hyderabad").json()
    b = client.get("/integrations/eraktkosh/inventory?city=Hyderabad").json()
    assert [bank["inventory"] for bank in a["blood_banks"]] == [
        bank["inventory"] for bank in b["blood_banks"]
    ]


# ----- GET /integrations/icmr-rdri/lookup -----


def test_icmr_lookup_returns_donors_with_full_shape(client: TestClient) -> None:
    body = client.get("/integrations/icmr-rdri/lookup").json()
    assert body["source"] == "icmr_rdri"
    assert body["status"] == "mocked"
    assert len(body["registered_donors"]) >= 5
    sample = body["registered_donors"][0]
    for field in (
        "registry_id", "name_initials", "blood_group",
        "kell_negative", "extended_phenotype", "city", "registered_year",
    ):
        assert field in sample


def test_icmr_lookup_kell_negative_filter(client: TestClient) -> None:
    body = client.get(
        "/integrations/icmr-rdri/lookup?kell_negative=true"
    ).json()
    assert body["filters"]["kell_negative"] == "True"
    for d in body["registered_donors"]:
        assert d["kell_negative"] is True


def test_icmr_lookup_blood_group_filter(client: TestClient) -> None:
    body = client.get(
        "/integrations/icmr-rdri/lookup?blood_group=B%2B"
    ).json()
    assert body["filters"]["blood_group"] == "B+"
    for d in body["registered_donors"]:
        assert d["blood_group"] == "B+"


def test_icmr_combined_filter_finds_aaravs_demo_match(client: TestClient) -> None:
    """Aarav is B+ Kell-negative — should return at least one RDRI record."""
    body = client.get(
        "/integrations/icmr-rdri/lookup?blood_group=B%2B&kell_negative=true&city=Hyderabad"
    ).json()
    assert len(body["registered_donors"]) >= 1
    for d in body["registered_donors"]:
        assert d["blood_group"] == "B+"
        assert d["kell_negative"] is True
        assert d["city"] == "Hyderabad"
