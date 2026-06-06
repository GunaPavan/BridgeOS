"""Integrations API: mock external services + status hub."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.integrations import eraktkosh, icmr_rdri
from app.schemas.integrations import (
    BloodBankStockOut,
    ERaktKoshInventoryResponse,
    ICMRLookupResponse,
    IntegrationsStatusList,
    IntegrationStatus,
    RegisteredRareDonorOut,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get(
    "",
    response_model=IntegrationsStatusList,
    summary="Status of every external integration",
)
def list_integrations() -> IntegrationsStatusList:
    """Return a status row for every external integration the system uses.

    Mock-status integrations are wired up; ``not_configured`` ones surface
    the env vars needed to go live. AWS Bedrock flips to ``connected``
    automatically when ``BEDROCK_REGION`` is set.
    """
    from app.agent.llm_client import (
        get_active_provider as _llm_provider,
        get_bedrock_model_for_task,
        DEFAULT_BEDROCK_SONNET,
        DEFAULT_BEDROCK_HAIKU,
    )
    from app.agent.embeddings import (
        get_active_provider as _embed_provider,
        DEFAULT_BEDROCK_TITAN,
    )

    bedrock_live = (
        _llm_provider() == "bedrock" and _embed_provider() == "bedrock_titan"
    )

    now = datetime.now(timezone.utc)
    items = [
        IntegrationStatus(
            key="eraktkosh",
            name="eRaktKosh — National Blood Bank Network",
            description=(
                "MoHFW/CDAC central blood-bank inventory across 3,800+ centres. "
                "Bridge OS pulls availability by city + blood group to inform "
                "transfusion routing."
            ),
            status="mocked",
            last_sync=now,
            sample_count=eraktkosh.sample_count(),
            docs_url="https://eraktkosh.mohfw.gov.in/",
            phase="Phase 8",
        ),
        IntegrationStatus(
            key="icmr_rdri",
            name="ICMR Rare Donor Registry (RDRI)",
            description=(
                "ICMR-NIIH registry for rare phenotypes (Kell-, Bombay, "
                "Rh-null, …). Critical for repeat-transfused thalassemia "
                "patients at risk of alloimmunisation."
            ),
            status="mocked",
            last_sync=icmr_rdri.last_sync(),
            sample_count=icmr_rdri.sample_count(),
            docs_url="https://www.niihindia.org/",
            phase="Phase 8",
        ),
        IntegrationStatus(
            key="whatsapp_business",
            name="WhatsApp Business API",
            description=(
                "Twilio-backed channel for donor confirmations, swap requests, "
                "and care-agent conversations. Routes through the existing "
                "REAN-built bot."
            ),
            status="not_configured",
            last_sync=None,
            sample_count=None,
            docs_url="https://www.twilio.com/whatsapp",
            phase="Phase 10",
        ),
        IntegrationStatus(
            key="aws_bedrock",
            name="AWS Bedrock — Multi-model AI layer",
            description=(
                "Unified AWS-native LLM provider. Routes chat to Claude "
                "Sonnet 4.5 (deep reasoning), intent classification to "
                "Claude Haiku 4.5 (fast + cheap), and memory embeddings to "
                "Amazon Titan Text v2 (1024-d). Anthropic Claude direct is "
                "the portable fallback when BEDROCK_REGION is unset."
            ),
            status="connected" if bedrock_live else "not_configured",
            last_sync=now if bedrock_live else None,
            sample_count=None,
            docs_url="https://docs.aws.amazon.com/bedrock/",
            phase="Care Agent",
        ),
    ]
    return IntegrationsStatusList(items=items, generated_at=now)


@router.get(
    "/eraktkosh/inventory",
    response_model=ERaktKoshInventoryResponse,
    summary="Mock eRaktKosh inventory query",
)
def eraktkosh_inventory(
    city: str | None = Query(None, description="Filter by city (case-insensitive)"),
    blood_group: str | None = Query(
        None,
        description="Filter centres that have units of this blood group (e.g. 'B+')",
    ),
) -> ERaktKoshInventoryResponse:
    banks = eraktkosh.fetch_inventory(city=city, blood_group=blood_group)
    return ERaktKoshInventoryResponse(
        fetched_at=datetime.now(timezone.utc),
        city_filter=city,
        blood_group_filter=blood_group,
        blood_banks=[BloodBankStockOut(**asdict(b)) for b in banks],
    )


@router.get(
    "/icmr-rdri/lookup",
    response_model=ICMRLookupResponse,
    summary="Mock ICMR Rare Donor Registry lookup",
)
def icmr_lookup(
    blood_group: str | None = Query(None),
    kell_negative: bool | None = Query(None),
    city: str | None = Query(None),
) -> ICMRLookupResponse:
    donors = icmr_rdri.lookup_donors(
        blood_group=blood_group, kell_negative=kell_negative, city=city
    )
    filters: dict[str, str] = {}
    if blood_group is not None:
        filters["blood_group"] = blood_group
    if kell_negative is not None:
        filters["kell_negative"] = str(kell_negative)
    if city is not None:
        filters["city"] = city
    return ICMRLookupResponse(
        fetched_at=datetime.now(timezone.utc),
        filters=filters,
        registered_donors=[RegisteredRareDonorOut(**asdict(d)) for d in donors],
    )
