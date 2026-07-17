# CFC Bakery — Baseline Floor (Phase 4)

Rolling-origin backtest, 3 monthly folds: 2026-04, 2026-05, 2026-06.
Metric = WMAPE (lower better). These are the floors the ML model must beat.

## Overall (all products)

| Baseline | WMAPE | MAE | Bias |
|---|---|---|---|
| moving_avg_7 | 0.401 | 2.70 | +0.14 |
| moving_avg_28 | 0.411 | 2.76 | +0.14 |
| naive_lag1 (yesterday) | 0.450 | 3.04 | +0.15 |
| dow_mean_28 (wkday avg) | 0.460 | 3.09 | +0.23 |
| seasonal_naive_7 (same wkday) | 0.528 | 3.54 | +0.23 |

**Best baseline: moving_avg_7 — WMAPE 0.401.** ML target: beat this by ≥20% (≤0.321).

## Best baseline (moving_avg_7) by ABC class

| Class | WMAPE | share of volume |
|---|---|---|
| A | 0.349 | 80% |
| B | 0.534 | 15% |
| C | 0.733 | 5% |

→ Class-A WMAPE is the number that matters most (80% of volume).

## All baselines × class (WMAPE)

| Baseline | A | B | C |
|---|---|---|---|
| naive_lag1 (yesterday) | 0.388 | 0.599 | 0.862 |
| seasonal_naive_7 (same wkday) | 0.465 | 0.704 | 0.949 |
| moving_avg_7 | 0.349 | 0.534 | 0.733 |
| moving_avg_28 | 0.359 | 0.550 | 0.749 |
| dow_mean_28 (wkday avg) | 0.408 | 0.607 | 0.815 |