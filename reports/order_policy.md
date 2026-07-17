# CFC Order Policy — Newsvendor (Phase 7)

DEMO econ: GM 35%, shelf-life 1d, salvage 0%. Edit `data/product_econ.csv` for real values.
Order plan: 608,261 (branch×product×day) rows over backtest folds.

## Critical ratio by ABC class
| Class | products | avg CR | median order/day | vol share |
|---|---|---|---|---|
| A | 70 | 0.35 | 5.0 | 75% |
| B | 83 | 0.35 | 1.0 | 19% |
| C | 131 | 0.35 | 1.0 | 5% |

## Order policy vs realised demand (cost, ₭)

| Policy | cost ₭ | stockout% | waste% | fill% | avg order |
|---|---|---|---|---|---|
| newsvendor (per-product CR) | 3,048,098,715 | 54.1 | 8.0 | 60.4 | 4.41 |
| flat P50 | 2,936,968,955 | 34.2 | 14.8 | 80.0 | 6.30 |
| flat P85 | 6,066,010,680 | 10.6 | 33.2 | 93.8 | 9.42 |
| baseline mov_avg_7 | 3,706,158,135 | 31.7 | 20.8 | 81.0 | 6.86 |

**Lowest cost: flat P50 — ₭2,936,968,955.** Newsvendor vs baseline ₭3,706,158,135 = +18%.
At flat GM 35% same-day spoilage, CR<0.5 → newsvendor≈lean order, close to P50 (matches Phase 6). Real per-product margin+shelf-life will spread CR → high-margin/long-shelf SKUs get more safety stock.
