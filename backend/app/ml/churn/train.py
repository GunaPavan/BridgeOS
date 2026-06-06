"""Train the multi-class churn classifier on real Blood Warriors data.

Run:
    python -m app.ml.churn.train --out models/churn

Reads from the active DB (so run `python -m scripts.seed --source ...` first).
Produces:
    models/churn/churn_model.joblib
    models/churn/churn_meta.joblib       (feature names + metrics)
    models/churn/churn_report.json       (full evaluation report)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sqlalchemy import select
from sqlalchemy.orm import Session
from xgboost import XGBClassifier

from app.db import SessionLocal
from app.ml.churn.features import FEATURE_NAMES, ChurnFeatures, extract_donor_features
from app.ml.churn.predictor import CLASS_NAMES
from app.models import Donor, DonorType, InactiveReason


@dataclass
class ChurnTrainingReport:
    n_total: int = 0
    n_active: int = 0
    n_not_donated_1y: int = 0
    n_limited_despite_calls: int = 0
    n_train: int = 0
    n_test: int = 0
    binary_auc: float = 0.0           # Active vs Inactive (one-vs-rest)
    macro_f1: float = 0.0
    weighted_f1: float = 0.0
    class_aucs: dict = field(default_factory=dict)
    classification_report: dict = field(default_factory=dict)
    confusion_matrix: list = field(default_factory=list)
    feature_importances: dict = field(default_factory=dict)
    feature_names: list = field(default_factory=list)
    cv_macro_f1_mean: float = 0.0
    cv_macro_f1_std: float = 0.0


def build_label(donor: Donor) -> int | None:
    """Map a donor row to one of the 3 classes — or None to exclude.

    Exclusion rules (the dataset has noise we don't want to train on):
      • Donors who never donated (total_donations == 0) and are not labeled
        Inactive — they're censored, not informative for churn.
      • Anyone with no donation history AND no outreach history — we can't
        say anything about them.
    """
    is_active = bool(donor.is_active)
    donations = int(donor.total_donations or 0)
    calls = int(donor.total_calls or 0)

    if is_active:
        # Only count Active donors who have *some* engagement signal
        if donations == 0 and calls == 0:
            return None  # uninformative
        return 0  # ACTIVE

    # Inactive — branch on labeled reason
    if donor.inactive_reason == InactiveReason.NOT_DONATED_1Y:
        return 1
    if donor.inactive_reason == InactiveReason.LIMITED_DESPITE_CALLS:
        return 2
    return None  # Inactive but no reason — exclude


def load_dataset(db: Session) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Build (X, y, donor_ids) arrays from the DB."""
    today = date.today()
    donors = db.execute(select(Donor)).scalars().all()

    X_rows: list[list[float]] = []
    y_rows: list[int] = []
    ids: list[str] = []

    for d in donors:
        label = build_label(d)
        if label is None:
            continue
        feats = extract_donor_features(d, today=today)
        X_rows.append(feats.as_list())
        y_rows.append(label)
        ids.append(str(d.id))

    return np.array(X_rows, dtype=np.float32), np.array(y_rows, dtype=np.int64), ids


def train(out_dir: Path, *, seed: int = 42) -> ChurnTrainingReport:
    """End-to-end training pipeline."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rpt = ChurnTrainingReport(feature_names=list(FEATURE_NAMES))

    with SessionLocal() as db:
        X, y, _ids = load_dataset(db)

    rpt.n_total = int(len(y))
    rpt.n_active = int((y == 0).sum())
    rpt.n_not_donated_1y = int((y == 1).sum())
    rpt.n_limited_despite_calls = int((y == 2).sum())
    print(
        f"Loaded {rpt.n_total} donors: "
        f"{rpt.n_active} active, {rpt.n_not_donated_1y} not-1y, "
        f"{rpt.n_limited_despite_calls} limited"
    )

    if rpt.n_total < 50 or min(rpt.n_active, rpt.n_not_donated_1y, rpt.n_limited_despite_calls) < 5:
        raise RuntimeError(
            f"Insufficient data for training: "
            f"need >=50 total and >=5 per class, got {rpt.n_total} / "
            f"{rpt.n_active}/{rpt.n_not_donated_1y}/{rpt.n_limited_despite_calls}"
        )

    # 80/20 stratified split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=seed
    )
    rpt.n_train = int(len(y_train))
    rpt.n_test = int(len(y_test))

    # Class-weighted training to handle imbalance
    class_counts = np.bincount(y_train, minlength=3)
    class_weights = {i: float(len(y_train) / (3 * max(c, 1))) for i, c in enumerate(class_counts)}
    sample_weight = np.array([class_weights[int(c)] for c in y_train], dtype=np.float32)

    print(f"Class weights: {class_weights}")

    model = XGBClassifier(
        objective="multi:softprob",
        num_class=3,
        n_estimators=200,
        max_depth=5,
        learning_rate=0.08,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=seed,
        eval_metric="mlogloss",
        tree_method="hist",
    )
    model.fit(X_train, y_train, sample_weight=sample_weight)

    # Evaluate
    probs = model.predict_proba(X_test)
    preds = probs.argmax(axis=1)

    rpt.macro_f1 = float(f1_score(y_test, preds, average="macro", zero_division=0))
    rpt.weighted_f1 = float(f1_score(y_test, preds, average="weighted", zero_division=0))

    # Binary AUC: Active (0) vs Inactive (1 or 2)
    y_test_binary = (y_test > 0).astype(int)
    p_inactive = probs[:, 1] + probs[:, 2]
    if len(np.unique(y_test_binary)) > 1:
        rpt.binary_auc = float(roc_auc_score(y_test_binary, p_inactive))

    # Per-class one-vs-rest AUC
    for cls in range(3):
        y_cls = (y_test == cls).astype(int)
        if len(np.unique(y_cls)) > 1:
            try:
                rpt.class_aucs[CLASS_NAMES[cls]] = float(
                    roc_auc_score(y_cls, probs[:, cls])
                )
            except Exception:
                pass

    rpt.classification_report = classification_report(
        y_test, preds, target_names=CLASS_NAMES,
        output_dict=True, zero_division=0,
    )
    rpt.confusion_matrix = confusion_matrix(y_test, preds).tolist()

    # Feature importances
    rpt.feature_importances = {
        name: float(imp)
        for name, imp in zip(FEATURE_NAMES, model.feature_importances_)
    }

    # 5-fold cross-validation for stability
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    cv_scores: list[float] = []
    for tr_idx, te_idx in skf.split(X, y):
        m = XGBClassifier(
            objective="multi:softprob", num_class=3,
            n_estimators=200, max_depth=5, learning_rate=0.08,
            subsample=0.85, colsample_bytree=0.85,
            random_state=seed, eval_metric="mlogloss", tree_method="hist",
        )
        sw = np.array([class_weights[int(c)] for c in y[tr_idx]], dtype=np.float32)
        m.fit(X[tr_idx], y[tr_idx], sample_weight=sw)
        cv_scores.append(
            float(f1_score(y[te_idx], m.predict(X[te_idx]), average="macro", zero_division=0))
        )
    rpt.cv_macro_f1_mean = float(np.mean(cv_scores))
    rpt.cv_macro_f1_std = float(np.std(cv_scores))

    # Save
    joblib.dump(model, out_dir / "churn_model.joblib")
    joblib.dump(
        {
            "feature_names": FEATURE_NAMES,
            "class_names": CLASS_NAMES,
            "metrics": {
                "binary_auc": rpt.binary_auc,
                "macro_f1": rpt.macro_f1,
                "weighted_f1": rpt.weighted_f1,
                "cv_macro_f1_mean": rpt.cv_macro_f1_mean,
                "cv_macro_f1_std": rpt.cv_macro_f1_std,
            },
        },
        out_dir / "churn_meta.joblib",
    )
    with open(out_dir / "churn_report.json", "w", encoding="utf-8") as f:
        json.dump(asdict(rpt), f, indent=2)

    return rpt


def main() -> int:
    parser = argparse.ArgumentParser(description="Train multi-class churn model.")
    parser.add_argument("--out", default="models/churn", help="Output directory.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out = Path(args.out)
    report = train(out, seed=args.seed)

    print()
    print("=" * 60)
    print("TRAINING REPORT")
    print("=" * 60)
    print(f"n_total           : {report.n_total}")
    print(f"n_active          : {report.n_active}")
    print(f"n_not_donated_1y  : {report.n_not_donated_1y}")
    print(f"n_limited_despite : {report.n_limited_despite_calls}")
    print(f"binary_auc        : {report.binary_auc:.4f}")
    print(f"macro_f1          : {report.macro_f1:.4f}")
    print(f"weighted_f1       : {report.weighted_f1:.4f}")
    print(f"cv_macro_f1       : {report.cv_macro_f1_mean:.4f} ± {report.cv_macro_f1_std:.4f}")
    print()
    print("Per-class AUCs:")
    for k, v in report.class_aucs.items():
        print(f"  {k:35s} : {v:.4f}")
    print()
    print("Top 5 features by importance:")
    for k, v in sorted(report.feature_importances.items(), key=lambda x: -x[1])[:5]:
        print(f"  {k:30s} : {v:.4f}")
    print()
    print(f"Artifacts saved to: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
