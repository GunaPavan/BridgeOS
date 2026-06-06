"""Reset DB schema and optionally ingest a dataset.

Usage:
    python -m scripts.seed                              # reset schema, empty DB
    python -m scripts.seed --source data/bw_2026.csv    # reset + ingest
    python -m scripts.seed --source data/bw_2026.json --format json

The synthetic generator that lived here previously is gone — Bridge OS now
uses the Blood Warriors-provided dataset via scripts/ingest_real_dataset.py.
If no --source is given this leaves you with an empty schema, ready for
ingest later.
"""

from __future__ import annotations

import argparse
import sys

from app.db import Base, SessionLocal, engine
from app.models import (  # noqa: F401 (register models)
    AgentMessage,
    Bridge,
    BridgeMembership,
    CohortMemory,
    Donor,
    DonorResponseEvent,
    Patient,
    ScheduleResolveLog,
    SlotSwapRequest,
    WhatsAppMessage,
)


def reset_schema() -> None:
    """Drop all tables and recreate from current ORM metadata."""
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Recreating tables...")
    Base.metadata.create_all(bind=engine)


def seed(source: str | None = None, fmt: str | None = None) -> int:
    """Reset schema; if source is given, ingest it."""
    reset_schema()
    if source is None:
        print(
            "Schema is empty. Provide --source path/to/dataset.csv to ingest "
            "Blood Warriors data, or use the API to load it interactively."
        )
        return 0

    from scripts.ingest_real_dataset import ingest_real_dataset

    with SessionLocal() as db:
        report = ingest_real_dataset(db, source_path=source, fmt=fmt)
    print(report.summary())
    if report.feature_patient_id:
        print(f"Feature patient picked: {report.feature_patient_id}")
    if report.errors:
        print(f"First 5 errors: {report.errors[:5]}")
    return 0 if not report.errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset Bridge OS schema and optionally ingest data.")
    parser.add_argument(
        "--source",
        default=None,
        help="Path to Blood Warriors dataset file (CSV or JSON). Omit to leave the DB empty.",
    )
    parser.add_argument("--format", choices=["csv", "json"], default=None)
    args = parser.parse_args()
    return seed(source=args.source, fmt=args.format)


if __name__ == "__main__":
    sys.exit(main())
