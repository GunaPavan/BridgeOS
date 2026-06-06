"""AWS Location Service client — reverse geocoding for donor / patient coords.

Wraps `boto3.client('location').search_place_index_for_position()` with a
DB-backed cache (GeocodeCache table) so we never re-pay for the same
coordinate. Designed for the Blood Warriors dataset which has thousands of
rows but only ~132 unique coordinates.

Usage:
    from app.integrations.aws_location import reverse_geocode

    city, state = reverse_geocode(db, lat=17.39, lng=78.46)
    # -> ("Hyderabad", "Telangana")

Configuration via env vars:
    AWS_LOCATION_PLACE_INDEX  default: "bridge-os-place-index"
    AWS_REGION                default: "us-east-1"

Behavior contract:
    - If lat/lng are None or 0/0, returns ("Unknown", "Unknown") without an
      API call.
    - If AWS credentials aren't configured or the call errors, returns
      ("Unknown", "Unknown") and logs the error — never raises. This keeps
      ingest robust in dev environments.
    - Successful resolutions are cached in the DB; subsequent calls with the
      same coord (rounded to 4 decimals) are free DB reads.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.geocode_cache import GeocodeCache

log = logging.getLogger(__name__)


# Cache the boto3 client at module level so we don't recreate it per call.
_location_client = None
_PLACE_INDEX_NAME = os.environ.get("AWS_LOCATION_PLACE_INDEX", "bridge-os-place-index")
_AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Precision: 4 decimal places ≈ 11 metres. Two raw coordinates that round to
# the same (lat, lng) share the cache row. Don't bump above 4 — you'll inflate
# the cache and call AWS more often.
_CACHE_PRECISION = 4


def _get_client():
    """Lazy-initialize the boto3 Location client. Returns None if boto3 or
    AWS credentials aren't available — caller handles the None case."""
    global _location_client
    if _location_client is None:
        try:
            import boto3  # lazy import keeps test envs clean

            _location_client = boto3.client("location", region_name=_AWS_REGION)
        except Exception as e:
            log.warning("AWS Location client init failed: %s", e)
            return None
    return _location_client


def reverse_geocode(
    db: Session,
    lat: Optional[float],
    lng: Optional[float],
) -> tuple[str, str]:
    """Resolve (lat, lng) to (city, state).

    Hits the DB cache first. On miss, calls AWS Location Service, persists the
    result, returns it. Always commits the cache row immediately so concurrent
    ingest workers benefit.

    Returns ("Unknown", "Unknown") for null/zero coords or any error path.
    """
    if lat is None or lng is None:
        return ("Unknown", "Unknown")
    # Treat 0/0 as "missing" — that's the equator/prime meridian which has no
    # population centre and signals "no real coords on file".
    if lat == 0.0 and lng == 0.0:
        return ("Unknown", "Unknown")

    lat_r = round(float(lat), _CACHE_PRECISION)
    lng_r = round(float(lng), _CACHE_PRECISION)

    cached = db.execute(
        select(GeocodeCache).where(
            GeocodeCache.lat_rounded == lat_r,
            GeocodeCache.lng_rounded == lng_r,
        )
    ).scalar_one_or_none()
    if cached is not None:
        return (cached.city or "Unknown", cached.state or "Unknown")

    # Cache miss — call AWS Location
    resolved = _call_aws_location(lat, lng)
    if resolved is None:
        return ("Unknown", "Unknown")
    city, state, country, full_address = resolved

    # Persist to cache
    try:
        row = GeocodeCache(
            lat_rounded=lat_r,
            lng_rounded=lng_r,
            city=city,
            state=state,
            country=country,
            full_address=full_address,
        )
        db.add(row)
        db.commit()
    except Exception as e:
        log.warning("Cache write failed for (%s, %s): %s", lat_r, lng_r, e)
        db.rollback()

    return (city or "Unknown", state or "Unknown")


def _call_aws_location(
    lat: float, lng: float
) -> Optional[tuple[str | None, str | None, str | None, str | None]]:
    """Live AWS Location call. Returns (city, state, country, full_address).

    Returns None on any error so the caller can fall back to "Unknown".
    """
    client = _get_client()
    if client is None:
        return None

    try:
        # NOTE: AWS Location expects [longitude, latitude] order (GeoJSON-style).
        response = client.search_place_index_for_position(
            IndexName=_PLACE_INDEX_NAME,
            Position=[lng, lat],
            MaxResults=1,
        )
    except Exception as e:
        log.warning(
            "AWS Location SearchPlaceIndexForPosition failed for (%s, %s): %s",
            lat, lng, e,
        )
        return None

    results = response.get("Results", [])
    if not results:
        return None
    place = results[0].get("Place", {})
    # IMPORTANT: Esri's response model for India:
    #   - SubRegion = city name (e.g. "Hyderabad")
    #   - Municipality = neighborhood / locality (e.g. "Mallepally")
    #   - Region = state (e.g. "Telangana")
    # We want SubRegion for the city display. Only fall back to Municipality
    # when SubRegion is missing (e.g. some rural coords).
    city = (
        place.get("SubRegion")
        or place.get("Municipality")
        or place.get("Neighborhood")
    )
    state = place.get("Region")
    country = place.get("Country")
    full_address = place.get("Label")
    return (city, state, country, full_address)


def warm_cache_for_coords(
    db: Session,
    coords: list[tuple[float, float]],
    *,
    progress: bool = True,
) -> dict[str, int]:
    """Resolve every unique coord in `coords` up-front so subsequent reads
    are pure DB hits. Use this from the ingest pipeline so we don't make
    AWS calls inline with row processing.

    Returns counters: {resolved, cached, failed}.
    """
    counters = {"resolved": 0, "cached": 0, "failed": 0}
    seen: set[tuple[float, float]] = set()
    total = len(coords)
    for i, (lat, lng) in enumerate(coords):
        if lat is None or lng is None:
            counters["failed"] += 1
            continue
        key = (round(lat, _CACHE_PRECISION), round(lng, _CACHE_PRECISION))
        if key in seen:
            counters["cached"] += 1
            continue
        seen.add(key)

        # Check DB cache first
        existing = db.execute(
            select(GeocodeCache).where(
                GeocodeCache.lat_rounded == key[0],
                GeocodeCache.lng_rounded == key[1],
            )
        ).scalar_one_or_none()
        if existing is not None:
            counters["cached"] += 1
            continue

        resolved = _call_aws_location(lat, lng)
        if resolved is None:
            counters["failed"] += 1
            continue
        city, state, country, full_address = resolved
        row = GeocodeCache(
            lat_rounded=key[0],
            lng_rounded=key[1],
            city=city,
            state=state,
            country=country,
            full_address=full_address,
        )
        db.add(row)
        counters["resolved"] += 1
        if progress and counters["resolved"] % 25 == 0:
            print(
                f"  Geocoded {counters['resolved']} unique coords "
                f"({i + 1}/{total} rows scanned)"
            )

    db.commit()
    return counters
