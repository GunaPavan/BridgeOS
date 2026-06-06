"""Bring ``Dataset.csv`` up to current date.

The original dataset is a snapshot anchored at **2025-08-31** (the most
recent ``last_contacted_date``). At wall-clock 2026-06-06 we're roughly
9 months past the snapshot, which is why every date field looks stale to
the allocator + the urgency math classifies every patient as critical-
overdue. The organisers signed off on us extending the dataset; this
script does that conservatively:

1. **Anchor detection** — find the max non-future, non-NULL date across
   the time-series columns (``last_contacted_date`` wins because it's
   the most-edited operational column).
2. **Compute shift** — ``shift_days = today - anchor``. Default target is
   wall-clock today, configurable via ``--target``.
3. **Shift every date column** forward by ``shift_days`` (handles 7
   parseable date columns including ``last_bridge_donation_date``).
4. **Clip future-dated junk** — the dataset has a few rows with
   ``last_donation_date = 2029-09-30`` that look like data-entry errors.
   Any shifted date that lands after ``today`` is clipped back to today
   minus a small offset so we don't poison the allocator with future
   donations.
5. **Simulate intermediate activity** — for each active row with prior
   donation history, add the donations that would plausibly have
   happened in the shift window:

       additional_donations = floor(shift_days / max(90, cycle_days))
       capped at 4 so we don't fabricate aggressive activity

   Each simulated donation bumps ``donations_till_date``, advances
   ``last_donation_date`` by ``cycle_days`` per donation, and bumps
   ``total_calls`` proportionally to preserve the calls/donations ratio.
6. **Recompute** ``next_eligible_date = last_donation_date + 90 days``.
7. **Patient-row transfusion bumps** — the 84 Patient rows get extra
   transfusions in the gap window via ``cycle_of_donations`` += K and
   their ``last_transfusion_date`` pushed forward.

Usage:

    python -m scripts.extend_dataset                            # write to data/Dataset.extended.csv
    python -m scripts.extend_dataset --target 2026-06-06        # explicit target date
    python -m scripts.extend_dataset --inplace                  # overwrite Dataset.csv

The original is always kept as ``Dataset.csv.bak`` when ``--inplace`` is used.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import math
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional


def _stable_bucket(key: str) -> int:
    """Deterministic 0–99 bucket from a string. Stable across Python processes
    (unlike ``hash()``, which uses a per-process salt for security).
    """
    digest = hashlib.md5(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % 100

logger = logging.getLogger(__name__)


# When extending the dataset we also stamp realistic Indian names so the UI
# never has to render "Patient A72875". These columns are appended to the
# CSV by ``extend()``; ingestion reads them straight off.
NAME_COLUMNS = ["first_name", "last_name"]


DATE_COLUMNS = [
    "last_transfusion_date",
    "expected_next_transfusion_date",
    "registration_date",
    "last_contacted_date",
    "last_donation_date",
    "next_eligible_date",
    "last_bridge_donation_date",
]

# How many fresh donations we're willing to fabricate per donor — we don't
# want the simulated counters to swamp the real signal.
MAX_SIMULATED_DONATIONS = 4
MAX_SIMULATED_TRANSFUSIONS = 12  # one patient could have ~9 months / 25 days ≈ 11 transfusions

CLINICAL_DEFERRAL_DAYS = 90


def _parse(s: str) -> Optional[date]:
    """Forgive every plausible date format the dataset uses."""
    if not s or s.strip() in ("NA", "null", "None", ""):
        return None
    s = s.strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _format(d: Optional[date]) -> str:
    return d.isoformat() if d is not None else ""


def detect_anchor(rows: list[dict], today: date) -> date:
    """Pick the snapshot anchor.

    Uses the max ``last_contacted_date`` because it's the most actively
    edited column in real operations. Ignores future-dated rows (the
    2029 junk).
    """
    contacted = [
        d for r in rows
        if (d := _parse(r.get("last_contacted_date", ""))) is not None
        and d <= today
    ]
    if not contacted:
        # Fallback — registration_date max
        contacted = [
            d for r in rows
            if (d := _parse(r.get("registration_date", ""))) is not None
            and d <= today
        ]
    if not contacted:
        raise RuntimeError(
            "Couldn't find any anchor date — every date column was NULL or future-dated."
        )
    return max(contacted)


def _shift(d: Optional[date], shift_days: int, *, cap_at: date) -> Optional[date]:
    """Shift a date forward, clipping at ``cap_at`` to handle junk + future dates."""
    if d is None:
        return None
    shifted = d + timedelta(days=shift_days)
    if shifted > cap_at:
        # Pre-shift the date was already future; clip to a sensible recent
        # past date (cap_at - some buffer) to keep the row useful.
        return cap_at - timedelta(days=15)
    return shifted


def _safe_int(s: str, default: int = 0) -> int:
    try:
        v = int(float(s))
        return max(0, v)
    except (ValueError, TypeError):
        return default


def _safe_float(s: str, default: float = 0.0) -> float:
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def extend_row(
    row: dict,
    *,
    shift_days: int,
    today: date,
    name_map: dict | None = None,
) -> dict:
    """Apply the shift + activity simulation to one row, returning a new dict."""
    out = dict(row)

    # 0) Stamp the deterministic, UNIQUE Indian name pre-assigned by
    #    ``assign_unique_names`` (called once before this loop). Falls back
    #    to the per-row ``generate_name`` if no map was supplied.
    external_id = out.get("user_id") or ""
    if name_map and external_id in name_map:
        first, last = name_map[external_id]
    else:
        from app.services.name_generator import generate_name
        gender_hint = (out.get("gender") or out.get("bridge_gender") or "").strip()
        full = generate_name(external_id, gender=gender_hint)
        parts = full.split(" ", 1)
        first, last = parts[0], parts[1] if len(parts) > 1 else ""
    out["first_name"] = first
    out["last_name"] = last

    # 1) Shift every date column
    for col in DATE_COLUMNS:
        parsed = _parse(out.get(col, ""))
        shifted = _shift(parsed, shift_days, cap_at=today)
        out[col] = _format(shifted)

    role = (out.get("role", "") or "").strip().lower()
    is_active = (out.get("user_donation_active_status", "") or "").strip().lower() == "active"
    is_patient = role == "patient"
    is_bridge_donor = role == "bridge donor"

    # 2) Simulate intermediate donations for active bridge donors with history
    if is_bridge_donor and is_active:
        prior_donations = _safe_int(out.get("donations_till_date", ""), 0)
        cycle_days_raw = _safe_int(out.get("frequency_in_days", ""), 0)
        cycle_days = max(CLINICAL_DEFERRAL_DAYS, cycle_days_raw if cycle_days_raw >= 30 else CLINICAL_DEFERRAL_DAYS)
        last_donation = _parse(out.get("last_donation_date", ""))

        if prior_donations >= 1 and last_donation is not None:
            additional = min(MAX_SIMULATED_DONATIONS, shift_days // cycle_days)
            if additional >= 1:
                new_donations = prior_donations + additional
                out["donations_till_date"] = str(new_donations)

                # Push last_donation_date forward by additional × cycle_days,
                # clipped at today - 1 day so the donor isn't "donating
                # tomorrow"
                new_last_donation = min(
                    last_donation + timedelta(days=additional * cycle_days),
                    today - timedelta(days=1),
                )
                out["last_donation_date"] = _format(new_last_donation)

                # Refresh derived next_eligible
                out["next_eligible_date"] = _format(
                    new_last_donation + timedelta(days=CLINICAL_DEFERRAL_DAYS)
                )

                # Bump last_bridge_donation_date for bridge participants
                if out.get("last_bridge_donation_date"):
                    out["last_bridge_donation_date"] = _format(new_last_donation)

                # Bump total_calls proportionally — donors get reminded each cycle
                prior_calls = _safe_int(out.get("total_calls", ""), 0)
                out["total_calls"] = str(prior_calls + additional)

                # Recompute calls/donations ratio
                if new_donations > 0:
                    out["calls_to_donations_ratio"] = f"{(prior_calls + additional) / new_donations:.2f}"

    # 3) Simulate intermediate transfusions for patient rows.
    #
    # We bump ``cycle_of_donations`` by the fabricated cycle count and SET
    # ``last_transfusion_date`` to a deterministic target so the gap to next
    # transfusion (= last_trans + cadence - today) lands in a controlled
    # urgency bucket. This is more direct than offset-from-shift because the
    # original ``last_transfusion_date`` values were already spread across
    # multiple months pre-anchor, so just adding offsets produced wildly
    # skewed urgency distributions (every patient overdue or every patient
    # planned, depending on the seed).
    #
    # Deterministic bucket distribution (via stable hash of user_id):
    #   • ~5%  bucket 0-5    → overdue (gap ≈ -3d)        — CRITICAL
    #   • ~10% bucket 5-15   → due today (gap ≈ 0d)        — CRITICAL
    #   • ~10% bucket 15-25  → due in 1-2d                  — CRITICAL/HIGH
    #   • ~15% bucket 25-40  → due in 3-7d                  — HIGH/MEDIUM
    #   • ~60% bucket 40-100 → due in cadence/2 to cadence  — PLANNED
    if is_patient:
        cadence_raw = _safe_int(out.get("frequency_in_days", ""), 0)
        cadence = max(7, cadence_raw if cadence_raw >= 7 else 21)
        prior_transfusions = _safe_int(out.get("cycle_of_donations", ""), 0)
        last_trans = _parse(out.get("last_transfusion_date", ""))

        if last_trans is not None and cadence > 0:
            additional = shift_days // cadence
            if additional >= 1:
                bucket_key = (out.get("user_id") or out.get("patient_id") or "") + "tx"
                bucket = _stable_bucket(bucket_key)
                # gap_target = days from today to next transfusion (negative = overdue).
                # Target operational distribution (≈84 active patients):
                #   • ~2% (≈2) — CRITICAL (gap ≤ 1)
                #   • ~5% (≈4) — HIGH     (gap 2 with cadence ≥ 14 ⇒ tier_2/HIGH)
                #   • ~6% (≈5) — MEDIUM   (gap 5 with cadence ≥ 15 ⇒ tier_3/MEDIUM)
                #   • ~87% (≈73) — PLANNED (rotation scheduler owns them; allocator skips)
                # That mirrors a clinic where most patients are well-spaced and
                # only a handful need same-cycle outreach.
                # NOTE on tier math: tier is decided by the engine using
                # gap AND gap/cadence. ~6 patients have cadence<14 — for them
                # gap=2 lands in MEDIUM (not HIGH) because ratio>0.15. We
                # absorb that spillover by shrinking the explicit MEDIUM
                # bucket span, so total MEDIUM ≈ 5.
                if bucket < 3:
                    gap_target = 0 if bucket % 2 else -1   # CRITICAL
                elif bucket < 8:
                    gap_target = 2                          # HIGH (or MEDIUM if cad<14)
                elif bucket < 11:
                    gap_target = 5                          # MEDIUM
                else:
                    # PLANNED bucket: pick a gap that's guaranteed > 7d so the
                    # allocator's MEDIUM cutoff doesn't pick these up. We
                    # scatter them between 8d and (cadence + 8d) so the
                    # patients table shows a varied "next transfusion" column.
                    base = max(8, cadence // 2)
                    gap_target = base + (bucket % max(1, cadence))

                # last_trans + cadence = today + gap_target
                # ⇒ last_trans = today + gap_target - cadence
                new_last_trans = today + timedelta(days=gap_target - cadence)
                # Safety: don't go absurdly far back (3 cadences max)
                floor_date = today - timedelta(days=3 * cadence)
                if new_last_trans < floor_date:
                    new_last_trans = floor_date

                out["cycle_of_donations"] = str(prior_transfusions + additional)
                out["last_transfusion_date"] = _format(new_last_trans)
                out["expected_next_transfusion_date"] = _format(
                    new_last_trans + timedelta(days=cadence)
                )

    return out


def extend(
    source_path: Path,
    target_path: Path,
    *,
    today: Optional[date] = None,
) -> dict:
    """Read source CSV, extend every row, write to target. Returns summary."""
    today = today or date.today()

    with open(source_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys()) if rows else []

    anchor = detect_anchor(rows, today)
    shift_days = (today - anchor).days
    if shift_days <= 0:
        raise RuntimeError(
            f"Anchor ({anchor}) is at or after target ({today}); nothing to extend."
        )

    # Pre-allocate one unique (first_name, last_name) per user_id so no two
    # rows share a name. We pass the row's gender (or bridge_gender for
    # patients, matching the ingest fallback) as the gender hint.
    from app.services.name_generator import assign_unique_names
    name_inputs = [
        (
            r.get("user_id") or "",
            (r.get("gender") or r.get("bridge_gender") or "").strip() or None,
        )
        for r in rows
    ]
    name_map = assign_unique_names(name_inputs)

    extended = [
        extend_row(r, shift_days=shift_days, today=today, name_map=name_map)
        for r in rows
    ]

    # Ensure first_name + last_name columns are in the written CSV. They're
    # inserted right after user_id (in declared order) so anyone eyeballing
    # the CSV sees the name next to the id it was derived from.
    out_fieldnames = list(fieldnames)
    if "user_id" in out_fieldnames:
        anchor_idx = out_fieldnames.index("user_id") + 1
    else:
        anchor_idx = len(out_fieldnames)
    insert_offset = 0
    for col in NAME_COLUMNS:
        if col not in out_fieldnames:
            out_fieldnames.insert(anchor_idx + insert_offset, col)
            insert_offset += 1

    with open(target_path, "w", newline="", encoding="utf-8") as f:
        # Use minimal quoting to match the original file style
        writer = csv.DictWriter(f, fieldnames=out_fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(extended)

    # Summary stats — what changed
    summary = {
        "anchor": anchor.isoformat(),
        "target": today.isoformat(),
        "shift_days": shift_days,
        "rows_total": len(rows),
        "rows_with_simulated_donations": sum(
            1 for src, out in zip(rows, extended)
            if _safe_int(out.get("donations_till_date", ""), 0)
            > _safe_int(src.get("donations_till_date", ""), 0)
        ),
        "rows_with_simulated_transfusions": sum(
            1 for src, out in zip(rows, extended)
            if _safe_int(out.get("cycle_of_donations", ""), 0)
            > _safe_int(src.get("cycle_of_donations", ""), 0)
        ),
        "future_dates_clipped": sum(
            1 for src in rows
            if (d := _parse(src.get("last_donation_date", ""))) is not None and d > today
        ),
        "names_added": sum(1 for r in extended if r.get("first_name")),
    }
    return summary


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Extend Dataset.csv to current date.")
    p.add_argument(
        "--source",
        default="data/Dataset.csv",
        help="Path to the source CSV (default: data/Dataset.csv).",
    )
    p.add_argument(
        "--target",
        default=None,
        help="Target date YYYY-MM-DD (default: wall-clock today).",
    )
    p.add_argument(
        "--output",
        default="data/Dataset.extended.csv",
        help="Output path (default: data/Dataset.extended.csv).",
    )
    p.add_argument(
        "--inplace",
        action="store_true",
        help=(
            "Overwrite the source CSV. The original is backed up to <source>.bak. "
            "Use this when you want the next `python -m scripts.seed --source <same path>` "
            "to ingest the extended version."
        ),
    )
    args = p.parse_args()

    source = Path(args.source).resolve()
    if not source.exists():
        logger.error("Source CSV not found: %s", source)
        return 1
    target_date = (
        datetime.strptime(args.target, "%Y-%m-%d").date() if args.target else date.today()
    )
    output = Path(args.output).resolve()

    summary = extend(source, output, today=target_date)
    logger.info(
        "Extended %d rows: anchor=%s → target=%s (shift +%dd)",
        summary["rows_total"], summary["anchor"], summary["target"], summary["shift_days"],
    )
    logger.info(
        "  simulated donations on %d rows, transfusions on %d rows, clipped %d future-dated junk rows",
        summary["rows_with_simulated_donations"],
        summary["rows_with_simulated_transfusions"],
        summary["future_dates_clipped"],
    )
    logger.info(
        "  stamped first_name + last_name on %d rows", summary.get("names_added", 0)
    )
    logger.info("Wrote %s", output)

    if args.inplace:
        backup = source.with_suffix(source.suffix + ".bak")
        shutil.copy2(source, backup)
        shutil.move(output, source)
        logger.info(
            "Overwrote %s in place (backup at %s).",
            source.name, backup.name,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
