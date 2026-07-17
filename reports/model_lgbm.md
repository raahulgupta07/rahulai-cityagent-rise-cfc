# CFC Bakery — LightGBM Quantile Model (Phase 5)

Train < 2026-04-01 (7,721,315 rows), test 2026-04..06 (608,261 rows).
Features: 37 (18 categorical incl BranchId/ProductId).

## P50 accuracy vs baseline floor

| Segment | LGBM WMAPE | Baseline | Improvement |
|---|---|---|---|
| Overall | 0.341 | 0.401 | +15% |
| Class A | 0.291 | 0.349 | +17% |
| Class B | 0.457 | 0.534 | +14% |
| Class C | 0.640 | 0.733 | +13% |

## Quantile calibration (coverage)

- P85 coverage: 85.5% (target ~85%)
- P95 coverage: 94.5% (target ~95%)
- P50 bias: -0.42

## Top 15 features (P50, gain)

- ProductId: 51107
- BranchId: 30000
- rmean_28: 12101
- lag_1: 6345
- rstd_28: 6100
- rmean_7: 5830
- rmean_14: 5367
- rstd_14: 4314
- rstd_7: 4255
- month: 4203
- dow_mean_28: 2282
- CatLvl3_Name: 2148
- dom: 1891
- lag_14: 1837
- rmax_28: 1702

## Verdict
LightGBM P50 **BEATS** baseline floor (0.341 vs 0.401). Target ≤0.321.