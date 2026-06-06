"""Self-calibrating ML thresholds against the live data distribution.

Replaces the hardcoded constants we had baked in against the synthetic donor
population (0.623 / 0.550 / 0.70 / 0.92 / 0.85). Those numbers are derived
from the p60 / p70 / p86 of the synthetic distribution, so they are wrong by
construction the moment we load Blood Warriors' real dataset.

This module:
1. Reads the current set of ACTIVE bridge memberships from the DB,
2. Runs the stability predictor across them,
3. Computes percentile-based cutoffs against the OBSERVED churn distribution,
4. Caches the result with a short TTL so we don't recompute on every request,
5. Falls back to neutral defaults (0.5 / 0.3 / 0.5 / 0.8 / 0.7) when the DB is
   empty (e.g. before dataset ingestion).

The percentiles themselves are stable product decisions — they're saying
"the bottom 60% of cohorts is stable, the top 14% is critical." It's the
NUMBERS associated with those percentiles that depend on the data, and this
module recomputes them from whatever data is present.

Public surface:
    get_thresholds(db) -> CalibratedThresholds
    invalidate_cache()  # for tests + after re-ingest

CalibratedThresholds exposes:
    stable_cutoff      avg_churn_90d < this  -> STABLE
    at_risk_cutoff     avg_churn_90d < this  -> AT_RISK   (>= stable_cutoff)
    at_risk_donor      individual donor churn_90d >= this -> "weak"
    urgency_critical_top   top_risk in weak list >= this -> critical
    urgency_high_top       top_risk >= this -> high
    urgency_critical_count len(weak) >= this -> critical
    urgency_high_count     len(weak) >= this -> high

The count thresholds remain ordinal-stable (4 weak donors > 3) regardless of
how heavy-tailed the underlying distribution is, so they stay hardcoded.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bridge, MembershipStatus


# Percentile decisions (product-level, not data-level).
# These bracket the bridge population into stable (60%) / at-risk (26%) / critical (14%).
STABLE_PERCENTILE_CUTOFF = 60     # avg_churn at p60 marks the at_risk boundary
AT_RISK_PERCENTILE_CUTOFF = 86    # avg_churn at p86 marks the critical boundary
PER_DONOR_AT_RISK_PERCENTILE = 70 # individual donor at p70 of churn is "weak"
URGENCY_CRITICAL_TOP_PERCENTILE = 70  # top-risk percentile that triggers critical
URGENCY_HIGH_TOP_PERCENTILE = 50      # top-risk percentile that triggers high

# Neutral defaults when no data exists yet (pre-ingestion).
NEUTRAL_DEFAULTS = {
    "stable_cutoff": 0.50,
    "at_risk_cutoff": 0.70,
    "at_risk_donor": 0.50,
    "urgency_critical_top": 0.80,
    "urgency_high_top": 0.65,
}

# Count thresholds are ordinal and data-independent.
URGENCY_CRITICAL_COUNT = 4
URGENCY_HIGH_COUNT = 3

# Cache for ~5 minutes — calibration is non-trivial (runs the predictor across
# every active bridge), so we don't want to recompute on every API request.
CACHE_TTL_SECONDS = 300


@dataclass(frozen=True)
class CalibratedThresholds:
    """Snapshot of thresholds derived from the current data distribution."""

    stable_cutoff: float
    at_risk_cutoff: float
    at_risk_donor: float
    urgency_critical_top: float
    urgency_high_top: float
    urgency_critical_count: int = URGENCY_CRITICAL_COUNT
    urgency_high_count: int = URGENCY_HIGH_COUNT
    sampled_at: datetime | None = None
    sample_size: int = 0
    is_neutral: bool = False  # True iff falling back to NEUTRAL_DEFAULTS

    @classmethod
    def neutral(cls) -> "CalibratedThresholds":
        return cls(
            stable_cutoff=NEUTRAL_DEFAULTS["stable_cutoff"],
            at_risk_cutoff=NEUTRAL_DEFAULTS["at_risk_cutoff"],
            at_risk_donor=NEUTRAL_DEFAULTS["at_risk_donor"],
            urgency_critical_top=NEUTRAL_DEFAULTS["urgency_critical_top"],
            urgency_high_top=NEUTRAL_DEFAULTS["urgency_high_top"],
            sampled_at=datetime.now(timezone.utc),
            sample_size=0,
            is_neutral=True,
        )


_cache: CalibratedThresholds | None = None
_cache_lock = Lock()


def invalidate_cache() -> None:
    """Force recalculation on next get_thresholds call. Use after ingest."""
    global _cache
    with _cache_lock:
        _cache = None


def get_thresholds(db: Session) -> CalibratedThresholds:
    """Return current thresholds, recalibrating if the cache has expired.

    Thread-safe under FastAPI's single-process-many-worker model: each worker
    keeps its own cache, which is fine for our scale (and even desirable —
    re-ingest invalidates per-worker on next request, no broadcast needed).
    """
    global _cache
    now = datetime.now(timezone.utc)
    with _cache_lock:
        if _cache is not None and _cache.sampled_at is not None:
            age = (now - _cache.sampled_at).total_seconds()
            if age < CACHE_TTL_SECONDS:
                return _cache
        fresh = _calibrate(db)
        _cache = fresh
        return fresh


def _calibrate(db: Session) -> CalibratedThresholds:
    """Run the stability predictor across all active cohorts and compute
    percentile-driven thresholds. Returns NEUTRAL_DEFAULTS on empty data
    or if the predictor fails to load (e.g. in test environments)."""

    # Lazy import to break a potential circular dep (stability.predictor
    # imports app.models which is fine, but be defensive).
    try:
        from app.ml.stability import extract_features, get_predictor
    except Exception:
        return CalibratedThresholds.neutral()

    predictor = get_predictor()
    if predictor is None:
        return CalibratedThresholds.neutral()

    bridges = db.execute(select(Bridge)).scalars().all()
    if not bridges:
        return CalibratedThresholds.neutral()

    today = date.today()
    avg_churns: list[float] = []          # one per bridge
    top_risks: list[float] = []           # one per bridge (max donor churn)
    per_donor_churns: list[float] = []    # every active donor

    for b in bridges:
        active = [
            m for m in b.memberships
            if m.status == MembershipStatus.ACTIVE.value
            or m.status == MembershipStatus.ACTIVE
        ]
        if not active:
            continue
        try:
            preds = predictor.predict_batch(
                [extract_features(m.donor, b, today) for m in active]
            )
        except Exception:
            continue
        churns = [p.churn_90d for p in preds]
        if not churns:
            continue
        avg_churns.append(statistics.mean(churns))
        top_risks.append(max(churns))
        per_donor_churns.extend(churns)

    if not avg_churns or not per_donor_churns:
        return CalibratedThresholds.neutral()

    return CalibratedThresholds(
        stable_cutoff=_percentile(avg_churns, STABLE_PERCENTILE_CUTOFF),
        at_risk_cutoff=_percentile(avg_churns, AT_RISK_PERCENTILE_CUTOFF),
        at_risk_donor=_percentile(per_donor_churns, PER_DONOR_AT_RISK_PERCENTILE),
        urgency_critical_top=_percentile(top_risks, URGENCY_CRITICAL_TOP_PERCENTILE),
        urgency_high_top=_percentile(top_risks, URGENCY_HIGH_TOP_PERCENTILE),
        sampled_at=datetime.now(timezone.utc),
        sample_size=len(avg_churns),
        is_neutral=False,
    )


def _percentile(values: list[float], p: int) -> float:
    """Linear-interpolation percentile. Pure stdlib so no numpy dep here."""
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    s = sorted(values)
    k = (p / 100.0) * (len(s) - 1)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    d = k - f
    return float(s[f] + (s[c] - s[f]) * d)
