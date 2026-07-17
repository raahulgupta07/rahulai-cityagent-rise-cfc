# CFC Drift Monitor (Phase 8)

Reference < 2026-05-24 (8,120,743 rows) vs recent >= 2026-05-24 (208,833 rows).

## Data drift — PSI per feature
| feature | PSI | status |
|---|---|---|
| y | 0.089 | ok |
| lag_7 | 0.072 | ok |
| rmean_28 | 0.146 | ok |
| rstd_28 | 0.127 | ok |
| ListPrice | 0.058 | ok |
| tmax_c | 1.573 | DRIFT |
| rain_mm | 2.252 | DRIFT |
| promo_active | n/a | n/a |
| dow | 0.007 | ok |

## Accuracy drift — champion WMAPE

- champion holdout WMAPE (train time): 0.319
- recent-window WMAPE (now): 0.310  (warn threshold 0.351)
- status: ok

## Verdict: **RETRAIN RECOMMENDED**
(data drift=yes, accuracy drift=no)