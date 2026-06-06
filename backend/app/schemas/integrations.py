"""Integrations API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


IntegrationStatusLiteral = Literal["mocked", "connected", "not_configured", "error"]


class IntegrationStatus(BaseModel):
    key: str = Field(description="Stable identifier")
    name: str
    description: str
    status: IntegrationStatusLiteral
    last_sync: Optional[datetime] = None
    sample_count: Optional[int] = Field(
        default=None,
        description="Number of records available in the mock dataset (if mocked)",
    )
    docs_url: Optional[str] = None
    phase: str = Field(description="Which Bridge OS phase activates this integration")


class IntegrationsStatusList(BaseModel):
    items: list[IntegrationStatus]
    generated_at: datetime


# --- eRaktKosh ---


class BloodBankStockOut(BaseModel):
    name: str
    city: str
    state: str
    lat: float
    lng: float
    phone: str
    inventory: dict[str, int]
    last_updated: datetime


class ERaktKoshInventoryResponse(BaseModel):
    source: str = "eraktkosh"
    status: IntegrationStatusLiteral = "mocked"
    fetched_at: datetime
    city_filter: Optional[str] = None
    blood_group_filter: Optional[str] = None
    blood_banks: list[BloodBankStockOut]


# --- ICMR RDRI ---


class RegisteredRareDonorOut(BaseModel):
    registry_id: str
    name_initials: str
    blood_group: str
    kell_negative: bool
    extended_phenotype: str
    city: str
    registered_year: int


class ICMRLookupResponse(BaseModel):
    source: str = "icmr_rdri"
    status: IntegrationStatusLiteral = "mocked"
    fetched_at: datetime
    filters: dict[str, str]
    registered_donors: list[RegisteredRareDonorOut]
