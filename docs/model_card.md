# Bridge OS — Model Card

This is the combined model card for the two ML models in production. Both
trained on the **real Blood Warriors dataset** (7,033 rows, March 2020 –
August 2025). The previous procedural / synthetic predictor has been
removed; everything in production now traces back to labeled real-world
data.

## Quick reference

| Model | Algorithm | Real-data sample | Metric | Inference (single) |
|-------|-----------|------------------|--------|---------------------|
| Multi-class Churn Classifier | XGBoost (multi:softprob) | 2,622 donors with labels | **AUC 0.979 / macro F1 0.810** | ~0.6 ms |
| Time-to-Event Survival | GradientBoostingSurvival (scikit-survival) | 6,949 donors / 682 events | **C-index 0.751** | ~0.3 ms |

Both models picked from algorithm bake-offs (10 churn + 7 survival
candidates) using Borda multi-criteria ranking — see `docs/bakeoff_methodology.md`.

---

## Multi-class Churn Classifier

### Purpose
Classify each donor into one of three engagement states so coordinators can
act with intent instead of just risk-flagging.

| Class | Population | Recommended action |
|-------|-----------:|---------------------|
| `active` | 1,940 | Continue normal cadence |
| `inactive_not_donated_1y` | 361 | Send a friendly reminder — donor is likely to convert |
| `inactive_limited_despite_calls` | 321 | Stop calling — try a different channel or accept loss |

The two inactive classes have distinct labeled reasons from Blood Warriors:
*"Not donated in last 1 year"* (forgot, still reachable) and *"Very limited
activity despite multiple calls"* (call fatigue — outreach failing). The
multi-class framing is what makes the predictions intervention-ready.

### Features (8)
The feature list was carefully chosen to **avoid label leakage** — fields
that mechanically define the inactive classes (`total_calls`,
`calls_to_donations_ratio`, `days_since_last_donation`) are excluded.

- `donations_till_date` — donation count
- `avg_cycle_days` — empirical donation rhythm
- `days_since_last_contact` — outreach recency
- `days_since_registration` — donor tenure
- `is_regular` — declared donor type
- `is_one_time`
- `has_blood_group` — engagement proxy (Guests often skip)
- `donated_earlier`

When trained with the leaky fields, the model hit AUC 1.000 — a clear sign
the labels were rule-defined. The leaky fields are dropped here.

### Training
- Stratified 80/20 split (class weights: 0.45 / 2.42 / 2.72)
- `n_estimators=300`, `max_depth=5`, `learning_rate=0.05`
- 5-fold cross-validation for stability check

### Held-out metrics
| Metric | Value |
|--------|-------|
| Test macro F1 | **0.810** |
| Test weighted F1 | 0.891 |
| Test binary AUC (Active vs Inactive) | **0.979** |
| Per-class AUC: Active | 0.979 |
| Per-class AUC: Not-donated-1Y | 0.945 |
| Per-class AUC: Limited-despite-calls | 0.967 |
| 5-fold CV macro F1 | 0.804 ± 0.022 |

### Top features by importance
1. `donated_earlier` (0.57)
2. `avg_cycle_days` (0.14)
3. `days_since_last_contact` (0.08)
4. `is_one_time` (0.075)
5. `donations_till_date` (0.066)

### Limitations
- Snapshot data — model cannot predict horizon-specific (30/60/90 day)
  probabilities the way old XGBoost claimed to. The `StabilityPrediction`
  back-compat shim approximates 60d/30d as `0.85 × churn_90d` and
  `0.60 × churn_90d` for callers that need a horizon, but the **honest**
  per-horizon signal comes from the survival model.
- Class imbalance ~6:1 — minority class recall is capped without more
  labeled data.

---

## Time-to-Event Survival Model

### Purpose
Predict, for each donor, the probability they remain *active* at 90 / 180 /
365 days from their last donation (or registration if never donated).
Provides a continuous risk score for prioritization.

### Features (7)
- `donations_till_date`
- `avg_cycle_days`
- `is_regular`
- `is_one_time`
- `has_blood_group`
- `donated_earlier`
- `log_total_donations`

### Survival framing
- **Duration** = days from last_donation_date (or registration) to today
- **Event** = 1 if donor is currently Inactive, 0 if Active (right-censored)
- **Population** = 6,949 donors total (682 events, 6,267 censored)

### Training
- `GradientBoostingSurvivalAnalysis` from scikit-survival
- `n_estimators=200`, `max_depth=4`, `learning_rate=0.05`
- Single 80/20 stratified split (single-fold; C-index doesn't translate
  cleanly to k-fold averaging)

### Held-out metrics
| Metric | Value |
|--------|-------|
| **C-index test** | **0.751** |
| C-index train | 0.806 |
| Train-test gap | 0.055 (moderate — acceptable) |
| Median survival days | 730+ |

### Why GradientBoostingSurvival won
Out of 7 survival models tested:

| Model | C-test | Inference | Why not winner |
|-------|-------:|----------:|----------------|
| **GradientBoostingSurvival** | **0.751** | **0.3 ms** | — picked: dominates on both axes |
| XGBoost AFT | 0.718 | 0.5 ms | +0.095 train-test gap (overfit risk) |
| RandomSurvivalForest | 0.674 | 47 ms | Too slow + lower C-index |
| Weibull AFT | 0.663 | 6.6 ms | Parametric assumption caps performance |
| LogNormal AFT | 0.660 | 7.1 ms | Same |
| LogLogistic AFT | 0.657 | 6.0 ms | Same |
| Cox PH | FAILED | — | Numerical convergence failure with 35 features |

### Limitations
- Survival probabilities at exactly 30 / 60 / 90 days are interpolated;
  the model's natural anchors are 90 / 180 / 365.
- Right-censoring rate is high (90%) — variance on minority-event
  predictions is wider than the C-index suggests.

---

## Where these models are surfaced in the product

| Surface | Model used | What it shows |
|---------|-----------|----------------|
| `/donors/{id}` (donor detail page) | Both | `ChurnPredictionCard` (class + action) + `SurvivalCurve` (90/180/365d) |
| `/bridges/{id}/stability` (legacy endpoint, shim) | Churn only | Aggregated per-donor predictions over the cohort |
| `/recommendations` and `/simulator` | Churn (via shim) | Composite-score ranking + what-if analysis |
| `/analytics` | Both | `MLStackOverview` card + `BakeoffTable` (top 5, expandable) |
| `/ml/model-metrics` (JSON) | Both | Live metrics for dashboard |
| `/ml/bakeoff/{model}` (JSON) | Either | Full algorithm comparison report |

## Reproducibility

Both bake-offs are deterministic given fixed seeds (42 by default).

```bash
# Train churn classifier
python -m app.ml.churn.bakeoff --out models/churn

# Train survival model
python -m app.ml.survival.bakeoff --out models/survival
```

Outputs:
- `models/churn/churn_model.joblib` — winner artifact
- `models/churn/churn_meta.joblib` — feature names, class labels, metrics
- `models/churn/bakeoff_report.json` — all 10 algorithms' metrics
- `models/survival/survival_model.joblib` — winner artifact
- `models/survival/survival_meta.joblib` — feature names, metrics
- `models/survival/bakeoff_report.json` — all 7 algorithms' metrics

## Removed: synthetic stability predictor

The previous `app/ml/stability/` directory held a procedurally-trained
XGBoost model with hand-crafted log-hazard coefficients. That code is gone
as of Module Integration 1. The `app.ml.stability` namespace remains as a
**thin compatibility adapter** that routes every call to the new churn
predictor, so old callers (recommendations engine, simulator engine,
scheduler) continue to work without modification — but every prediction
now comes from a model trained on real Blood Warriors data.

See `app/ml/stability/__init__.py` for the adapter source.
