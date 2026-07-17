# CFC Bakery — Demand Profile (Phase 2 EDA)

Generated from `demand_panel.parquet` (7,084,242 rows), 2023-01-01 → 2026-06-23.

## 1. Overall scale
- Net units sold (all time): **58,804,247**
- Revenue (all time): **207,973,924,791 Ks**
- Active branches: **84** | active products: **3580** | days: **1270**
- Avg lines/day: 5,578

## 2. Trend over time
![monthly](figs/monthly_units.png)

Net units by year:
- 2023: 15,626,194
- 2024: 16,940,945
- 2025: 16,876,887
- 2026: 9,360,220

2023→2025 growth: **+8%**. (2026 partial → June.)

## 3. Day-of-week pattern
![dow](figs/dow.png)

- Peak day: **Sunday** (52,445/day) | weakest: **Monday** (43,218/day)
- Peak/trough ratio: **1.21×** → day-of-week is a strong driver.

## 4. Channel & segment mix
By channel:
- Seasons: 50,301,872 units, 174,820,394,398 Ks (85.5%)
- NBH: 3,887,373 units, 13,269,299,557 Ks (6.6%)
- Bistro: 3,066,034 units, 11,217,842,521 Ks (5.2%)
- Gong Cha: 1,308,201 units, 7,139,288,464 Ks (2.2%)
- CD: 108,107 units, 1,214,072,850 Ks (0.2%)
- LS: 67,228 units, 139,560,000 Ks (0.1%)

## 5. Product category (CatLvl1)
- FG: 58,679,621 units, 3479.0 SKUs
- All: 124,605 units, 100.0 SKUs
- ADM: 21 units, 1.0 SKUs

## 6. Concentration
Top 10 branches by units:
- Shwe Gone Daing Branch: 2,322,797
- Thamine Branch: 2,299,872
- Myay Ni Gone Branch: 2,241,903
- Mawlamyine Branch: 2,145,821
- Hledan Center Branch: 1,752,846
- Wai Zayan Dar Branch: 1,730,000
- North Dagon Pin Lon Sittaung Branch: 1,638,142
- Insein Phawt Kan Branch: 1,613,531
- HAGL Branch: 1,551,159
- Hlaing Thar Yar Branch: 1,509,155

Top 10 branches = **32%** of units. Top 20 = 55%.

Top 10 products by units:
- Golden Chicken Floss: 3,393,457
- Egg Pudding: 3,212,021
- Today's Brew: 2,727,456
- Croissant 6'S: 2,587,257
- Egg Cake: 1,134,527
- Chicken Curry Puff: 1,101,641
- Hot Dog Bun: 1,040,408
- Chicken Nugget Charcoal Mini Burger: 1,035,565
- Cheese Puff: 1,024,020
- Tuna & Sweet Corn Sandwich: 943,406

## 7. Demand pattern classification (per branch×SKU series)
Total active series (branch×SKU): **77,941**

| Pattern | Series | % series | % of volume |
|---|---|---|---|
| smooth | 26,985 | 35% | 71% |
| erratic | 2,954 | 4% | 8% |
| intermittent | 41,336 | 53% | 16% |
| lumpy | 6,646 | 9% | 5% |
| dead | 20 | 0% | 0% |

→ **smooth/erratic** = forecast with LightGBM. **intermittent/lumpy** = Croston/SBA. (Syntetos-Boylan-Croston cuts.)

## 8. ABC / XYZ (product-level)
ABC (by cumulative volume):
- A: 99 products (3%)
- B: 311 products (9%)
- C: 3170 products (89%)

Class A products (99) drive 80% of volume → focus model effort here.
XYZ stability (monthly CV): X(stable)=848, Y=929, Z(volatile)=924.

## 9. Festival / holiday effect
- Normal day avg: 46,045 units
- Public holiday avg: 49,205 (+7% vs normal)
- Thingyan window avg: 42,395 (-8% vs normal)
→ Festivals materially shift demand → calendar features essential.

## 10. Sparsity & lifecycle
- Series classed 'dead' (no positive sales): 20
- Median active span per series: 32 days
- Series active <90 days (new/short-lived): 52,458

→ Cold-start handling needed for new branch/SKU; backfill zeros on calendar for active series.

## Modeling implications
- Global LightGBM quantile on smooth/erratic A/B series (bulk of volume).
- Croston/SBA for intermittent/lumpy long tail.
- Calendar (dow + festivals) + weather + promo features mandatory.
- Focus accuracy on Class-A; tolerate coarser tail.
- Complete daily calendar per active series (fill zeros) before features.
