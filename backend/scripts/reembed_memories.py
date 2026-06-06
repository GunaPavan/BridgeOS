"""Migrate cohort memories from the previous embedding provider to Titan v2.

Cohort memory rows persist `embedding_provider` and `embedding_dim`, so a
provider switch (e.g. local hashbag → Titan) leaves old rows invisible to
retrieval until they're re-embedded. This script does that opt-in upgrade.

Cost: ~$0.00002 per memory row (Titan input pricing). Free for the operator
to NOT run — old memories simply stop returning from retrieval until they're
re-embedded by this script.

Usage:
    BEDROCK_REGION=us-east-1 python -m scripts.reembed_memories
    BEDROCK_REGION=us-east-1 python -m scripts.reembed_memories --limit 100
    BEDROCK_REGION=us-east-1 python -m scripts.reembed_memories --dry-run
"""

from __future__ import annotations

import argparse
import sys
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.embeddings import embed, get_active_provider
from app.db import SessionLocal
from app.models.cohort_memory import CohortMemory


def reembed(
    db: Session, *, target_provider: str, limit: int | None = None, dry_run: bool = False
) -> tuple[int, int]:
    """Re-embed every memory whose embedding_provider != target_provider.

    Returns (n_updated, n_skipped).
    """
    stmt = select(CohortMemory).where(CohortMemory.embedding_provider != target_provider)
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = db.execute(stmt).scalars().all()

    updated = 0
    skipped = 0
    for i, row in enumerate(rows, start=1):
        try:
            result = embed(row.summary)
        except Exception as exc:
            print(f"  [{i}/{len(rows)}] FAILED on memory {row.id}: {exc}")
            skipped += 1
            continue

        if dry_run:
            print(
                f"  [{i}/{len(rows)}] would re-embed {row.id} "
                f"({row.embedding_provider}/{row.embedding_dim} -> "
                f"{result.provider}/{result.dim})"
            )
            continue

        row.embedding = result.vector
        row.embedding_provider = result.provider
        row.embedding_dim = result.dim
        updated += 1

        # Commit in small batches so a crash doesn't lose all work
        if i % 50 == 0:
            db.commit()
            print(f"  [{i}/{len(rows)}] committed batch...")

    if not dry_run:
        db.commit()
    return updated, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-embed cohort memories.")
    parser.add_argument("--limit", type=int, default=None, help="Cap on rows to migrate.")
    parser.add_argument("--dry-run", action="store_true", help="Print plan, don't write.")
    args = parser.parse_args()

    provider = get_active_provider()
    if provider == "local":
        print(
            "Active embedding provider is 'local' (no Bedrock / OpenAI env set). "
            "There's no point re-embedding to the same fallback. Set BEDROCK_REGION."
        )
        return 1

    print(f"Re-embedding memories to provider: {provider}")
    started = time.time()
    with SessionLocal() as db:
        updated, skipped = reembed(
            db,
            target_provider=provider,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    elapsed = time.time() - started
    print(f"\nDone in {elapsed:.1f}s — {updated} updated, {skipped} skipped.")
    if args.dry_run:
        print("(dry-run — nothing was persisted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
