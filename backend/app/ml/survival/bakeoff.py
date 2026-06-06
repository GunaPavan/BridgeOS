"""Multi-algorithm bake-off for the time-to-event survival model.

Survival framing:
    duration = days from last_donation_date (or registration_date) to today
    event    = 1 if donor is Inactive, 0 if Active (right-censored)

Algorithms tested:
    - Cox Proportional Hazards (lifelines)
    - Weibull AFT (lifelines)
    - Log-Normal AFT (lifelines)
    - Log-Logistic AFT (lifelines)
    - Random Survival Forest (scikit-survival)
    - Gradient Boosting Survival (scikit-survival)
    - XGBoost survival:aft

Selection criterion: best concordance index (C-index) on the hold-out fold.

Usage:
    python -m app.ml.survival.bakeoff --out models/survival
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.ml.features_v2 import FEATURE_NAMES, build_feature_matrix
from app.ml.survival.features import compute_duration_event
from app.models import BridgeMembership, Donor

warnings.filterwarnings("ignore")


@dataclass
class ModelResult:
    name: str
    c_index_train: float = 0.0
    c_index_test: float = 0.0
    train_time_ms: float = 0.0
    inference_time_us: float = 0.0
    failed: bool = False
    error: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def load_survival_dataset(db: Session):
    """Build feature matrix + (duration, event) arrays for the entire donor pool."""
    today = date.today()
    all_donors = db.execute(select(Donor)).scalars().all()
    memberships = set(db.execute(select(BridgeMembership.donor_id)).scalars().all())
    mem_lookup = {d.id: (d.id in memberships) for d in all_donors}

    keep = []
    duration_event = []
    for d in all_donors:
        de = compute_duration_event(d, today=today)
        if de is None or de[0] <= 0:
            continue
        keep.append(d)
        duration_event.append(de)

    X, geo = build_feature_matrix(keep, today=today, fit_geo=True, membership_lookup=mem_lookup)
    arr = np.array(duration_event, dtype=np.int64)
    durations = arr[:, 0]
    events = arr[:, 1]
    return X, durations, events, geo


def c_index_safe(durations, events, predicted_risk):
    """Concordance index — higher = better. Handles ties safely."""
    from lifelines.utils import concordance_index
    try:
        # higher risk should mean SHORTER survival, so we pass -risk if model
        # output is itself a survival time. Most models output risk where
        # higher = more likely to event, which is what concordance_index expects
        # *negated* (it expects predicted SURVIVAL TIME). We'll pass -risk.
        return float(concordance_index(durations, -np.asarray(predicted_risk), events))
    except Exception:
        return 0.0


def fit_cox(X, durations, events, X_test, dur_test, ev_test):
    from lifelines import CoxPHFitter
    df = pd.DataFrame(X, columns=FEATURE_NAMES)
    df["duration"] = durations
    df["event"] = events
    cph = CoxPHFitter(penalizer=0.01)
    cph.fit(df, duration_col="duration", event_col="event", show_progress=False)

    df_test = pd.DataFrame(X_test, columns=FEATURE_NAMES)
    risk_train = cph.predict_partial_hazard(df).values.ravel()
    risk_test = cph.predict_partial_hazard(df_test).values.ravel()
    return cph, risk_train, risk_test


def fit_aft(distribution: str):
    """Build a fitter factory for a parametric AFT family."""
    from lifelines import (
        WeibullAFTFitter,
        LogNormalAFTFitter,
        LogLogisticAFTFitter,
    )
    table = {
        "weibull": WeibullAFTFitter,
        "lognormal": LogNormalAFTFitter,
        "loglogistic": LogLogisticAFTFitter,
    }
    Fitter = table[distribution]

    def _fit(X, durations, events, X_test, dur_test, ev_test):
        df = pd.DataFrame(X, columns=FEATURE_NAMES)
        df["duration"] = durations
        df["event"] = events
        aft = Fitter(penalizer=0.01)
        aft.fit(df, duration_col="duration", event_col="event", show_progress=False)
        df_test = pd.DataFrame(X_test, columns=FEATURE_NAMES)
        # AFT models predict expected lifetime; higher = better. We need risk
        # (higher = worse), so use the negative log expectation.
        med_train = aft.predict_median(df).values.ravel()
        med_test = aft.predict_median(df_test).values.ravel()
        # Some medians are inf — clip them
        med_train = np.nan_to_num(med_train, nan=10**6, posinf=10**6)
        med_test = np.nan_to_num(med_test, nan=10**6, posinf=10**6)
        return aft, -med_train, -med_test  # negate so "higher = higher risk"

    return _fit


def fit_rsf(X, durations, events, X_test, dur_test, ev_test):
    """Random Survival Forest from scikit-survival."""
    from sksurv.ensemble import RandomSurvivalForest

    y = np.array(
        [(bool(e), float(d)) for d, e in zip(durations, events)],
        dtype=[("event", bool), ("duration", float)],
    )
    rsf = RandomSurvivalForest(n_estimators=200, max_depth=8, random_state=42, n_jobs=-1)
    rsf.fit(X, y)
    risk_train = rsf.predict(X)
    risk_test = rsf.predict(X_test)
    return rsf, risk_train, risk_test


def fit_gbs(X, durations, events, X_test, dur_test, ev_test):
    """Gradient Boosting Survival from scikit-survival."""
    from sksurv.ensemble import GradientBoostingSurvivalAnalysis

    y = np.array(
        [(bool(e), float(d)) for d, e in zip(durations, events)],
        dtype=[("event", bool), ("duration", float)],
    )
    gbs = GradientBoostingSurvivalAnalysis(
        n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42,
    )
    gbs.fit(X, y)
    risk_train = gbs.predict(X)
    risk_test = gbs.predict(X_test)
    return gbs, risk_train, risk_test


def fit_xgb_aft(X, durations, events, X_test, dur_test, ev_test):
    """XGBoost survival:aft — fastest survival model and often strongest."""
    import xgboost as xgb

    # XGBoost AFT needs y_lower and y_upper. For uncensored events:
    # both equal to duration. For censored: y_lower=duration, y_upper=inf.
    y_lower = durations.astype(np.float32)
    y_upper = np.where(events == 1, durations, np.inf).astype(np.float32)

    dtrain = xgb.DMatrix(X)
    dtrain.set_float_info("label_lower_bound", y_lower)
    dtrain.set_float_info("label_upper_bound", y_upper)

    params = {
        "objective": "survival:aft",
        "eval_metric": "aft-nloglik",
        "aft_loss_distribution": "normal",
        "aft_loss_distribution_scale": 1.20,
        "tree_method": "hist",
        "learning_rate": 0.05,
        "max_depth": 5,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "verbosity": 0,
    }
    booster = xgb.train(params, dtrain, num_boost_round=300)

    risk_train = booster.predict(dtrain)
    dtest = xgb.DMatrix(X_test)
    risk_test = booster.predict(dtest)
    # AFT outputs expected lifetime; negate for risk
    return booster, -risk_train, -risk_test


def main() -> int:
    parser = argparse.ArgumentParser(description="Survival model bake-off.")
    parser.add_argument("--out", default="models/survival")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print("Loading dataset + building expanded feature matrix...")
    with SessionLocal() as db:
        X, durations, events, geo = load_survival_dataset(db)
    print(f"  X shape: {X.shape}")
    print(f"  events: {int(events.sum())} / {len(events)} (censored: {int((events==0).sum())})")
    print(f"  feature count: {len(FEATURE_NAMES)}")
    print()

    # 80/20 split stratified by event
    indices = np.arange(len(X))
    train_idx, test_idx = train_test_split(
        indices, test_size=0.2, stratify=events, random_state=args.seed
    )
    X_train, X_test = X[train_idx], X[test_idx]
    dur_train, dur_test = durations[train_idx], durations[test_idx]
    ev_train, ev_test = events[train_idx], events[test_idx]

    fitters: list[tuple[str, Callable]] = [
        ("CoxPH", fit_cox),
        ("Weibull_AFT", fit_aft("weibull")),
        ("LogNormal_AFT", fit_aft("lognormal")),
        ("LogLogistic_AFT", fit_aft("loglogistic")),
        ("XGBoost_AFT", fit_xgb_aft),
        ("RandomSurvivalForest", fit_rsf),
        ("GradientBoostingSurvival", fit_gbs),
    ]

    results: list[ModelResult] = []
    models: dict = {}

    print("Running bake-off:")
    print(f"{'Model':28s} {'C-train':>10s} {'C-test':>10s} {'Train(ms)':>12s} {'Inf(us)':>10s}")
    print("-" * 75)

    for name, fitter in fitters:
        r = ModelResult(name=name)
        try:
            t0 = time.perf_counter()
            model, risk_train, risk_test = fitter(
                X_train, dur_train, ev_train, X_test, dur_test, ev_test,
            )
            r.train_time_ms = (time.perf_counter() - t0) * 1000

            # Per-prediction inference time
            t0 = time.perf_counter()
            for _ in range(500):
                _ = _predict_one(model, X_test[:1], name)
            r.inference_time_us = (time.perf_counter() - t0) * 1e6 / 500

            r.c_index_train = c_index_safe(dur_train, ev_train, risk_train)
            r.c_index_test = c_index_safe(dur_test, ev_test, risk_test)
            models[name] = model
            print(f"{name:28s} {r.c_index_train:>10.4f} {r.c_index_test:>10.4f} {r.train_time_ms:>12.1f} {r.inference_time_us:>10.1f}")
        except Exception as e:
            r.failed = True
            r.error = str(e)
            print(f"{name:28s} FAILED: {e}")
        results.append(r)

    valid = [r for r in results if not r.failed]
    valid.sort(key=lambda r: -r.c_index_test)
    if not valid:
        print("No survival models succeeded.")
        return 1

    print()
    print("=" * 75)
    print(f"WINNER: {valid[0].name}")
    print(f"  C-index test : {valid[0].c_index_test:.4f}")
    print(f"  C-index train: {valid[0].c_index_train:.4f}")
    print(f"  Inference    : {valid[0].inference_time_us:.1f} us/prediction")
    print("=" * 75)

    # Persist
    with open(out / "bakeoff_report.json", "w") as f:
        json.dump([r.as_dict() for r in results], f, indent=2)

    # Retrain winner on FULL data
    winner_name = valid[0].name
    winner_fitter = dict(fitters)[winner_name]
    final_model, _, _ = winner_fitter(X, durations, events, X, durations, events)

    joblib.dump(final_model, out / "survival_model.joblib")
    joblib.dump(
        {
            "winner": winner_name,
            "feature_names": FEATURE_NAMES,
            "metrics": {
                "c_index": valid[0].c_index_test,
                "c_index_train": valid[0].c_index_train,
                "n_events": int(events.sum()),
                "n_censored": int((events == 0).sum()),
                "inference_us_per_prediction": valid[0].inference_time_us,
            },
            "geo_clusterer": geo,
        },
        out / "survival_meta.joblib",
    )
    print(f"Winner saved to {out / 'survival_model.joblib'}")
    return 0


def _predict_one(model, X_one, name: str):
    """Best-effort prediction for benchmarking."""
    if name.endswith("_AFT") and not name.startswith("XGBoost"):
        df = pd.DataFrame(X_one, columns=FEATURE_NAMES)
        return model.predict_median(df).values
    if name == "CoxPH":
        df = pd.DataFrame(X_one, columns=FEATURE_NAMES)
        return model.predict_partial_hazard(df).values
    if name == "XGBoost_AFT":
        import xgboost as xgb
        return model.predict(xgb.DMatrix(X_one))
    return model.predict(X_one)  # RSF/GBS direct


if __name__ == "__main__":
    sys.exit(main())
