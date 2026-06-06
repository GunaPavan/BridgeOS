"""Train the Cox PH survival model on real Blood Warriors data.

Run:
    python -m app.ml.survival.train --out models/survival
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter
from lifelines.utils import concordance_index
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.ml.survival.features import (
    FEATURE_NAMES,
    compute_duration_event,
    extract_survival_features,
)
from app.models import Donor


@dataclass
class SurvivalTrainingReport:
    n_total: int = 0
    n_events: int = 0          # actual inactives observed
    n_censored: int = 0
    c_index: float = 0.0       # concordance — survival's AUC-equivalent
    median_survival_days: float = 0.0
    coefficients: dict = field(default_factory=dict)
    hazard_ratios: dict = field(default_factory=dict)
    p_values: dict = field(default_factory=dict)
    feature_names: list = field(default_factory=list)


def build_training_frame(db: Session) -> pd.DataFrame:
    """Build the survival DataFrame: features + duration + event."""
    today = date.today()
    rows: list[dict] = []
    for d in db.execute(select(Donor)).scalars().all():
        de = compute_duration_event(d, today=today)
        if de is None:
            continue
        duration, event = de
        if duration <= 0:
            continue
        feat = extract_survival_features(d).as_dict()
        feat["duration"] = duration
        feat["event"] = event
        rows.append(feat)
    return pd.DataFrame(rows)


def train(out_dir: Path, *, penalizer: float = 0.01) -> SurvivalTrainingReport:
    """End-to-end survival model training."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rpt = SurvivalTrainingReport(feature_names=list(FEATURE_NAMES))

    with SessionLocal() as db:
        df = build_training_frame(db)

    rpt.n_total = int(len(df))
    rpt.n_events = int(df["event"].sum())
    rpt.n_censored = int((df["event"] == 0).sum())
    print(
        f"Loaded {rpt.n_total} donors: "
        f"{rpt.n_events} events (inactive), {rpt.n_censored} censored (active)"
    )

    if rpt.n_events < 20:
        raise RuntimeError(f"Too few events for Cox PH: {rpt.n_events} (need >= 20)")

    # Cox PH with L2 penalty for stability
    cph = CoxPHFitter(penalizer=penalizer)
    cph.fit(df, duration_col="duration", event_col="event", show_progress=False)

    # C-index (concordance) is survival's AUC
    rpt.c_index = float(cph.concordance_index_)

    # Median survival (when 50% of the population is expected to be inactive)
    try:
        median = cph.predict_median(df[FEATURE_NAMES]).median()
        rpt.median_survival_days = float(median) if not pd.isna(median) else 0.0
    except Exception:
        rpt.median_survival_days = 0.0

    rpt.coefficients = {k: float(v) for k, v in cph.params_.items()}
    rpt.hazard_ratios = {k: float(np.exp(v)) for k, v in cph.params_.items()}
    rpt.p_values = {k: float(v) for k, v in cph.summary["p"].items()}

    # Save
    joblib.dump(cph, out_dir / "survival_model.joblib")
    joblib.dump(
        {
            "feature_names": FEATURE_NAMES,
            "metrics": {
                "c_index": rpt.c_index,
                "n_events": rpt.n_events,
                "n_censored": rpt.n_censored,
                "median_survival_days": rpt.median_survival_days,
            },
        },
        out_dir / "survival_meta.joblib",
    )
    with open(out_dir / "survival_report.json", "w", encoding="utf-8") as f:
        json.dump(asdict(rpt), f, indent=2)

    return rpt


def main() -> int:
    parser = argparse.ArgumentParser(description="Train Cox PH survival model.")
    parser.add_argument("--out", default="models/survival")
    parser.add_argument("--penalizer", type=float, default=0.01)
    args = parser.parse_args()

    out = Path(args.out)
    rpt = train(out, penalizer=args.penalizer)

    print()
    print("=" * 60)
    print("TRAINING REPORT")
    print("=" * 60)
    print(f"n_total           : {rpt.n_total}")
    print(f"n_events          : {rpt.n_events}")
    print(f"n_censored        : {rpt.n_censored}")
    print(f"C-index           : {rpt.c_index:.4f}")
    print(f"median_survival   : {rpt.median_survival_days:.1f} days")
    print()
    print("Hazard ratios (>1 = increases inactive risk, <1 = protective):")
    for k, v in sorted(rpt.hazard_ratios.items(), key=lambda x: -abs(np.log(x[1]))):
        p = rpt.p_values.get(k, 1.0)
        sig = " ***" if p < 0.001 else (" **" if p < 0.01 else (" *" if p < 0.05 else ""))
        print(f"  {k:30s} : HR={v:.4f}, p={p:.4g}{sig}")
    print()
    print(f"Artifacts saved to: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
