# CFC Service-Level vs Waste Tradeoff (Phase 7)

Order = demand quantile at target service level. Pick the dial mgmt wants.

| target service | order quantile | stockout% | waste% | fill% | cost ₭ |
|---|---|---|---|---|---|
| 30% | ~P30 | 57.9 | 6.8 | 52.6 | 3,311,515,555 |
| 50% | ~P50 | 34.2 | 14.8 | 80.0 | 2,936,968,955 |
| 70% | ~P70 | 18.2 | 25.6 | 89.7 | 4,400,981,655 |
| 85% | ~P85 | 10.6 | 33.2 | 93.8 | 6,066,010,680 |
| 95% | ~P95 | 4.1 | 45.7 | 97.3 | 10,068,618,740 |

Higher service → fewer stockouts but waste cost climbs. Cost-min sits where marginal margin saved = marginal spoilage. At GM35% same-day that's a low quantile.
