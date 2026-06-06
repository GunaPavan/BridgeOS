"""Multi-algorithm bake-off for the multi-class churn classifier.

Runs every reasonable model on the same train/test split and ranks them by
5-fold CV macro F1 (the metric that's hardest to game on imbalanced data).

Algorithms tested:
  - Logistic Regression (baseline interpretable)
  - Random Forest
  - Extra Trees
  - Gradient Boosting (sklearn)
  - XGBoost
  - LightGBM
  - CatBoost
  - MLP (neural net)
  - SVM (RBF kernel)
  - KNN

Selection criterion: best mean(CV macro F1) across 5 stratified folds.
Saves a `bakeoff_report.json` ranking all models + the winner's model file.

Usage:
    python -m app.ml.churn.bakeoff --out models/churn
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

import joblib
import numpy as np
from sklearn.ensemble import (
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.ml.churn.predictor import CLASS_NAMES
from app.ml.features_v2 import FEATURE_NAMES, build_feature_matrix
from app.models import BridgeMembership, Donor, InactiveReason

warnings.filterwarnings("ignore")


@dataclass
class ModelResult:
    name: str
    cv_macro_f1_mean: float
    cv_macro_f1_std: float
    test_macro_f1: float
    test_weighted_f1: float
    test_binary_auc: float
    test_per_class_auc: dict = field(default_factory=dict)
    train_time_ms: float = 0.0
    inference_time_us: float = 0.0  # per-prediction
    test_confusion: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def build_label(donor: Donor) -> int | None:
    is_active = bool(donor.is_active)
    donations = int(donor.total_donations or 0)
    calls = int(donor.total_calls or 0)

    if is_active:
        if donations == 0 and calls == 0:
            return None
        return 0
    if donor.inactive_reason == InactiveReason.NOT_DONATED_1Y:
        return 1
    if donor.inactive_reason == InactiveReason.LIMITED_DESPITE_CALLS:
        return 2
    return None


def load_dataset(db: Session):
    """Load X, y, donors, and a refit clusterer."""
    today = date.today()
    all_donors = db.execute(select(Donor)).scalars().all()
    # Membership lookup
    memberships = db.execute(
        select(BridgeMembership.donor_id)
    ).scalars().all()
    mem_set = set(memberships)
    mem_lookup = {d.id: (d.id in mem_set) for d in all_donors}

    # Filter to labeled rows
    keep = []
    y_rows = []
    for d in all_donors:
        lbl = build_label(d)
        if lbl is None:
            continue
        keep.append(d)
        y_rows.append(lbl)

    X, geo = build_feature_matrix(
        keep, today=today, fit_geo=True, membership_lookup=mem_lookup
    )
    y = np.array(y_rows, dtype=np.int64)
    return X, y, geo


def make_models(class_weights: dict, seed: int = 42):
    """Return list of (name, fitter_factory)."""
    # XGBoost
    from xgboost import XGBClassifier

    # LightGBM
    from lightgbm import LGBMClassifier

    # CatBoost
    from catboost import CatBoostClassifier

    def xgb():
        return XGBClassifier(
            objective="multi:softprob", num_class=3,
            n_estimators=300, max_depth=5, learning_rate=0.05,
            subsample=0.85, colsample_bytree=0.85,
            random_state=seed, eval_metric="mlogloss",
            tree_method="hist", verbosity=0,
        )

    def lgbm():
        return LGBMClassifier(
            objective="multiclass", num_class=3,
            n_estimators=300, max_depth=-1, num_leaves=31,
            learning_rate=0.05, subsample=0.85, colsample_bytree=0.85,
            random_state=seed, verbosity=-1,
        )

    def cat():
        return CatBoostClassifier(
            iterations=300, depth=5, learning_rate=0.05,
            loss_function="MultiClass", random_seed=seed,
            verbose=False,
        )

    def rf():
        return RandomForestClassifier(
            n_estimators=400, max_depth=12, class_weight="balanced",
            random_state=seed, n_jobs=-1,
        )

    def et():
        return ExtraTreesClassifier(
            n_estimators=400, max_depth=15, class_weight="balanced",
            random_state=seed, n_jobs=-1,
        )

    def gbm():
        return GradientBoostingClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            random_state=seed,
        )

    def lr():
        return Pipeline([
            ("scale", StandardScaler()),
            ("lr", LogisticRegression(
                solver="lbfgs", max_iter=1000,
                class_weight="balanced", random_state=seed,
            )),
        ])

    def mlp():
        return Pipeline([
            ("scale", StandardScaler()),
            ("mlp", MLPClassifier(
                hidden_layer_sizes=(64, 32),
                activation="relu", solver="adam",
                max_iter=300, random_state=seed,
            )),
        ])

    def svm():
        return Pipeline([
            ("scale", StandardScaler()),
            ("svm", SVC(
                kernel="rbf", C=1.0, probability=True,
                class_weight="balanced", random_state=seed,
            )),
        ])

    def knn():
        return Pipeline([
            ("scale", StandardScaler()),
            ("knn", KNeighborsClassifier(n_neighbors=15, weights="distance", n_jobs=-1)),
        ])

    return [
        ("XGBoost", xgb),
        ("LightGBM", lgbm),
        ("CatBoost", cat),
        ("RandomForest", rf),
        ("ExtraTrees", et),
        ("GradientBoosting", gbm),
        ("LogisticRegression", lr),
        ("MLP", mlp),
        ("SVM_RBF", svm),
        ("KNN", knn),
    ]


def evaluate(model, X, y, X_train, X_test, y_train, y_test, sample_weight):
    """Train and produce a ModelResult."""
    t0 = time.perf_counter()
    try:
        model.fit(X_train, y_train, sample_weight=sample_weight)
    except (TypeError, ValueError):
        # Pipelines don't accept sample_weight directly; some models reject it too
        model.fit(X_train, y_train)
    train_ms = (time.perf_counter() - t0) * 1000

    # Per-prediction inference time
    t0 = time.perf_counter()
    for _ in range(500):
        _ = model.predict(X_test[:1])
    inf_us = (time.perf_counter() - t0) * 1e6 / 500

    probs = model.predict_proba(X_test) if hasattr(model, "predict_proba") else None
    preds = model.predict(X_test)
    if hasattr(preds, "ravel"):
        preds = preds.ravel()
    preds = preds.astype(int)

    macro = float(f1_score(y_test, preds, average="macro", zero_division=0))
    weighted = float(f1_score(y_test, preds, average="weighted", zero_division=0))

    binary_auc = 0.0
    per_class = {}
    if probs is not None and probs.shape[1] == 3:
        y_bin = (y_test > 0).astype(int)
        p_inactive = probs[:, 1] + probs[:, 2]
        if len(np.unique(y_bin)) > 1:
            binary_auc = float(roc_auc_score(y_bin, p_inactive))
        for cls in range(3):
            y_cls = (y_test == cls).astype(int)
            if len(np.unique(y_cls)) > 1:
                try:
                    per_class[CLASS_NAMES[cls]] = float(roc_auc_score(y_cls, probs[:, cls]))
                except Exception:
                    pass

    conf = confusion_matrix(y_test, preds).tolist()

    return train_ms, inf_us, macro, weighted, binary_auc, per_class, conf


def cv_score(model_factory, X, y, seed: int) -> tuple[float, float]:
    """5-fold stratified CV macro F1."""
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    scores = []
    for tr_idx, te_idx in skf.split(X, y):
        m = model_factory()
        # Class weights for this fold
        counts = np.bincount(y[tr_idx], minlength=3)
        weights = {i: float(len(y[tr_idx]) / (3 * max(c, 1))) for i, c in enumerate(counts)}
        sw = np.array([weights[int(c)] for c in y[tr_idx]], dtype=np.float32)
        try:
            m.fit(X[tr_idx], y[tr_idx], sample_weight=sw)
        except (TypeError, ValueError):
            m.fit(X[tr_idx], y[tr_idx])
        preds = m.predict(X[te_idx])
        if hasattr(preds, "ravel"):
            preds = preds.ravel()
        scores.append(float(f1_score(y[te_idx], preds.astype(int), average="macro", zero_division=0)))
    return float(np.mean(scores)), float(np.std(scores))


def main() -> int:
    parser = argparse.ArgumentParser(description="Churn model bake-off.")
    parser.add_argument("--out", default="models/churn")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print("Loading dataset + building expanded feature matrix...")
    with SessionLocal() as db:
        X, y, geo = load_dataset(db)
    print(f"  X shape: {X.shape}, y shape: {y.shape}")
    print(f"  classes: {dict(zip(*np.unique(y, return_counts=True)))}")
    print(f"  feature count: {len(FEATURE_NAMES)}")
    print()

    # Stratified 80/20 split for hold-out evaluation
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=args.seed
    )
    counts = np.bincount(y_train, minlength=3)
    weights = {i: float(len(y_train) / (3 * max(c, 1))) for i, c in enumerate(counts)}
    sw = np.array([weights[int(c)] for c in y_train], dtype=np.float32)

    models = make_models(weights, seed=args.seed)
    results: list[ModelResult] = []

    print("Running bake-off:")
    print(f"{'Model':25s} {'CV F1':>10s} {'TestF1':>10s} {'AUC':>8s} {'Train(ms)':>12s} {'Inf(us)':>10s}")
    print("-" * 80)

    for name, factory in models:
        try:
            cv_mean, cv_std = cv_score(factory, X, y, seed=args.seed)
            m = factory()
            train_ms, inf_us, macro, weighted, bin_auc, per_class, conf = evaluate(
                m, X, y, X_train, X_test, y_train, y_test, sw
            )
            r = ModelResult(
                name=name,
                cv_macro_f1_mean=cv_mean,
                cv_macro_f1_std=cv_std,
                test_macro_f1=macro,
                test_weighted_f1=weighted,
                test_binary_auc=bin_auc,
                test_per_class_auc=per_class,
                train_time_ms=train_ms,
                inference_time_us=inf_us,
                test_confusion=conf,
            )
            results.append(r)
            print(f"{name:25s} {cv_mean:>7.4f}±{cv_std:.3f} {macro:>10.4f} {bin_auc:>8.4f} {train_ms:>12.1f} {inf_us:>10.1f}")
        except Exception as e:
            print(f"{name:25s} FAILED: {e}")

    # Multi-criterion ranking. Pure CV F1 mean ties LightGBM and XGBoost
    # within noise (±0.002), so we add tiebreakers:
    #   1. CV macro F1 mean (primary signal)
    #   2. Test macro F1 (held-out generalization)
    #   3. -log10(inference_us)  (faster = better, only matters at noise tier)
    # The weights below are chosen so a 0.005 F1 gap dominates a 10x speed gap.
    import math
    def _rank_key(r):
        return -(
            r.cv_macro_f1_mean * 1000
            + r.test_macro_f1 * 100
            + max(0.0, 5.0 - math.log10(max(1.0, r.inference_time_us)))
        )
    results.sort(key=_rank_key)
    print()
    print("=" * 80)
    print(f"WINNER: {results[0].name}")
    print(f"  CV macro F1     : {results[0].cv_macro_f1_mean:.4f} ± {results[0].cv_macro_f1_std:.4f}")
    print(f"  Test macro F1   : {results[0].test_macro_f1:.4f}")
    print(f"  Test binary AUC : {results[0].test_binary_auc:.4f}")
    print(f"  Inference       : {results[0].inference_time_us:.1f} us/prediction")
    print("=" * 80)

    # Persist results
    with open(out / "bakeoff_report.json", "w") as f:
        json.dump([r.as_dict() for r in results], f, indent=2)

    # Retrain winner on FULL data and save
    winner_factory = dict(models)[results[0].name]
    winner = winner_factory()
    full_counts = np.bincount(y, minlength=3)
    full_weights = {i: float(len(y) / (3 * max(c, 1))) for i, c in enumerate(full_counts)}
    full_sw = np.array([full_weights[int(c)] for c in y], dtype=np.float32)
    try:
        winner.fit(X, y, sample_weight=full_sw)
    except (TypeError, ValueError):
        winner.fit(X, y)

    joblib.dump(winner, out / "churn_model.joblib")
    joblib.dump(
        {
            "winner": results[0].name,
            "feature_names": FEATURE_NAMES,
            "class_names": CLASS_NAMES,
            "metrics": {
                "binary_auc": results[0].test_binary_auc,
                "macro_f1": results[0].test_macro_f1,
                "weighted_f1": results[0].test_weighted_f1,
                "cv_macro_f1_mean": results[0].cv_macro_f1_mean,
                "cv_macro_f1_std": results[0].cv_macro_f1_std,
                "inference_us_per_prediction": results[0].inference_time_us,
            },
            "geo_clusterer": geo,
        },
        out / "churn_meta.joblib",
    )
    print(f"Winner saved to {out / 'churn_model.joblib'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
