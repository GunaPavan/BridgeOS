"""Geocode cache — persists (lat, lng) → (city, state, country) so we don't
re-call AWS Location Service for the same coordinate.

Blood Warriors' dataset has 132 unique coordinates across 6,949 rows. Without
caching, every ingest re-pings AWS Location 132 times. With this table, the
first ingest pings 132 times (cost ~$0.07), and every subsequent ingest is
a pure DB read (cost $0). Cache key is (lat, lng) rounded to 4 decimal
places (~11m precision — good enough for city-level resolution).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import GUID

import uuid


class GeocodeCache(Base):
    """One row per resolved coordinate. Lookup by rounded (lat, lng)."""

    __tablename__ = "geocode_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )

    # Rounded to 4 decimals — used as the cache key.
    # Two different raw coords rounding to the same 4-dp pair will share the cache.
    lat_rounded: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    lng_rounded: Mapped[float] = mapped_column(Float, nullable=False, index=True)

    # Resolution output
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str | None] = mapped_column(String(128), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_address: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Provenance
    provider: Mapped[str] = mapped_column(
        String(32), default="aws_location", nullable=False
    )
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("lat_rounded", "lng_rounded", name="uq_geocode_coord"),
    )

    def __repr__(self) -> str:
        return (
            f"<GeocodeCache ({self.lat_rounded}, {self.lng_rounded}) "
            f"-> {self.city}, {self.state}>"
        )
