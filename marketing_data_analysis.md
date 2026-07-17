# Marketing Data Analysis — Loyalty Program Files

Source files (moved into this folder):
- `Loyalty Program current v3.xlsx`
- `Loyalty Program current v4.xlsx`

## What the files actually are
Promotion / loyalty **campaign logs** — NOT sales transactions. One row = one promo campaign.

Both files: single sheet `Sheet1`, same 6 columns.

| Column | Meaning | Example |
|---|---|---|
| `ID` | Campaign ID | 238 |
| `Items` | "<number> Promos" — redemption/item count for that campaign | `46836 Promos` |
| `Program Name` | Human description | "Buy Any 3 Sweet Bun only with 7,000 Ks" |
| `Program Type` | `Promotions` or `Buy X Get Y` | Promotions |
| `Start Date` | Campaign start (datetime, has hour) | 2026-04-14 06:00:00 |
| `End date` | Campaign end (datetime, has hour) | 2026-04-16 19:00:00 |

## Volume
| | v3 | v4 |
|---|---|---|
| Rows (campaigns) | 103 | 21 |
| Program Types | Promotions 69, Buy X Get Y 34 | Promotions 17, Buy X Get Y 4 |
| Items sum | 156,147 | 140,768 |
| Items mean | 1,516 | 6,703 |
| Items max | 46,836 | 114,218 (Markdown 50% Daily 7pm) |
| Date span | 2024-12-08 → 2026-04-16 | 2026-01-26 → 2026-05-31 |
| Median duration | 65 hrs (~3 days) | 113 hrs |

## Key findings
- **v3 and v4 are disjoint** — 0 overlapping IDs. v4 = 21 *different* campaigns, not a newer version of v3. Treat as **append**, not replace. Combined = 124 campaigns.
- **`Items` = redemption count**, the closest thing to a sales/demand signal in here. Big "Markdown Promotion 50% (Daily 7pm)" = 114k redemptions → recurring daily evening markdown, huge volume driver.
- Campaigns are **short + bursty** (median ~3 days, some run weeks/months e.g. May Born, Mother's Day).
- Heavy bakery focus: "Sweet Bun" promos dominate, plus drinks (Milk Tea, Today's Brew) and seasonal (Valentine, Mother's Day, May Born).
- Times have **hour precision** (e.g. 19:00 = 7pm markdown). Promo effect is intraday, not just daily.

## What's MISSING for forecasting
These files alone CANNOT train a demand model. No:
- per-outlet breakdown (which of the 50–100 outlets ran/redeemed each promo)
- per-SKU sales units per day
- daily sales baseline (non-promo demand)
- price / discount % as clean numeric
- product master (SKU → category, shelf life)

This data is a **covariate source**, not the target.

## How it plugs into the forecasting plan
Use as the **promo feature layer** (`plan.md` → Marketing data features):

1. Explode each campaign into a daily calendar: for each date in `[Start, End]`, mark `promo_active=1`.
2. Derive features per `day` (and per `outlet`/`SKU` once those joins exist):
   - `promo_active` flag
   - `promo_type` (Promotions vs Buy X Get Y)
   - `n_active_promos` that day
   - `promo_intensity` = redemptions (`Items`) / duration
   - `is_markdown_evening` flag (the recurring 7pm 50% markdown — strong intraday driver)
   - seasonal/event flag from name (Valentine, Mother's Day, May Born, New Opening)
3. Parse `Program Name` to tag affected product family (Sweet Bun / Drink / Merchandising) → join to SKU master later.

## Next data needed (to actually build model)
1. **Daily sales** per outlet per SKU (the target).
2. **Outlet master** (id, location, size).
3. **SKU master** (id, name, category, shelf life, price).
4. Optionally clean promo↔SKU↔outlet mapping.

Once daily sales arrive → merge promo calendar on date → build LightGBM quantile pipeline (`plan.md` Stage 2).
