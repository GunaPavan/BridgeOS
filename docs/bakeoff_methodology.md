# Bake-off Methodology

This document explains how we pick algorithms for the production ML models.

## Why a bake-off?

A single-model fit can win on one metric and lose on three. Borda count
(named after Jean-Charles de Borda, 1770) ranks candidates by summing
reciprocal ranks across every metric we care about. A model that's
top-3 on **all** metrics beats one that's #1 on one metric and #5 on others.

This is the same idea behind the Eurovision voting system and search-engine
re-ranking, applied to "which churn classifier should be in production?"

## Per-model criteria

### Churn classifier (10 algorithms tested)

| Metric | Direction | Why it matters |
|--------|-----------|----------------|
| CV macro F1 mean | higher | Holdout-equivalent class-balanced quality across 5 folds |
| CV macro F1 std | lower | Stability across splits — high std = lucky single fit |
| Test macro F1 | higher | True generalization on the never-seen 20% |
| Test binary AUC | higher | Active-vs-inactive separability (more interpretable than F1) |
| Inference latency | lower | Real-time fit (<5ms target for webhooks) |

Algorithms tested:
1. XGBoost (multi:softprob)
2. LightGBM
3. CatBoost
4. Random Forest
5. Extra Trees
6. Gradient Boosting (sklearn)
7. Logistic Regression
8. MLP (neural network)
9. SVM (RBF kernel)
10. KNN

### Survival model (7 algorithms tested)

| Metric | Direction | Why it matters |
|--------|-----------|----------------|
| C-index test | higher | Survival's AUC equivalent — concordance between predicted and observed durations |
| C-index train | (context) | Compared to test to compute overfit gap |
| Train-test gap | lower | Overfit detector — large gap = train memorized |
| Inference latency | lower | Real-time fit |

Algorithms tested:
1. Cox Proportional Hazards (lifelines)
2. Weibull AFT (lifelines)
3. Log-Normal AFT (lifelines)
4. Log-Logistic AFT (lifelines)
5. XGBoost `survival:aft`
6. Random Survival Forest (scikit-survival)
7. Gradient Boosting Survival (scikit-survival)

## Multi-criteria ranking (Borda)

For each model family, every candidate gets ranked separately on each metric.
We then sum reciprocal ranks:

```
score(candidate) = sum over metrics of  1 / rank_on_that_metric
```

Higher score = better overall. Ties are common when two candidates trade
positions across metrics; that's the *point* — Borda surfaces consistency,
not dominance on a single dimension.

### Worked example (churn, top-3)

| Algorithm | Rank by CV F1 | Rank by Test F1 | Rank by AUC | Rank by latency | Sum |
|-----------|---:|---:|---:|---:|---:|
| **XGBoost** | 2 | 2 | 1 | 8 | 1/2 + 1/2 + 1/1 + 1/8 = **2.125** |
| LightGBM | 1 | 5 | 4 | 9 | 1/1 + 1/5 + 1/4 + 1/9 = 1.561 |
| GradientBoosting | 4 | 1 | 3 | 7 | 1/4 + 1/1 + 1/3 + 1/7 = 1.726 |

XGBoost wins because it's top-3 on CV F1, Test F1, AND AUC simultaneously,
while LightGBM and GradientBoosting are each #1 on a different metric but
worse on the others.

## Why not just a single criterion?

Single-metric ranking is how you accidentally ship LightGBM at 5.7×
inference latency because it won CV F1 by 0.002 — within noise. Multi-
criteria forces you to look at the whole picture before saving the artifact.

## Reproducibility

Both bake-offs are deterministic given fixed seeds (seed=42).

```bash
python -m app.ml.churn.bakeoff --out models/churn
python -m app.ml.survival.bakeoff --out models/survival
```

Bake-off reports are persisted as `models/{churn,survival}/bakeoff_report.json`
so the `/ml/bakeoff/{model}` endpoint can serve them to the `/analytics` UI.

## See also

- `app/ml/churn/bakeoff.py` — churn bake-off implementation
- `app/ml/survival/bakeoff.py` — survival bake-off implementation
- `docs/model_card.md` — combined model card with held-out metrics
- `components/ui/bakeoff-table.tsx` — frontend rendering
