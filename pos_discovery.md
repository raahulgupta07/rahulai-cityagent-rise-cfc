# POS Data Discovery — 2026-06-24

## Big finding: POS line-item data EXISTS
The SQL endpoint hosts **6 databases** (not just CityPlatforms):
`CityPlatforms`, `CMHL_BI_DB`, **`CMHL_POS_DB`**, `HUB_REPORTING_DB`, `HUB_STAGING_DB`, `master`.
Cross-database queries WORK from this login (3-part name `DB.schema.table`).

`CMHL_POS_DB.dbo` has two POS sales tables with full product + quantity detail:

### `SalesDetails` — supermarket POS
- **1,162,738,057 rows** (1.16 billion), 157 locations, 169,916 SKUs, through 2026-06-23.
- Locations = City Mart (CM*) + Ocean (OC*) supermarkets. Codes match loyalty branches (CMGV=Golden Valley, CMWZYD=Wai Zayan Dar, CMPYAY65=Pyay 6.5mi).
- Columns: HeaderSK, DetailSK, Location, LocationName, SlipNo, CounterName, CashierName,
  DocumentDate (varchar YYYYMMDD), DocumentTime, **Barcode, StockCode, Description, SubCode, UOM**,
  Ratio, Price, **Qty**, Discount, MemberDiscount, Amount, TaxAmount, NetAmount, MemberID.

### `MCSSalesDetails` — convenience (City Express) POS
- **262,854,623 rows**, 286 locations (E### codes), 6,091 SKUs, 2019 → 2026-06-23.
- Products = energy drinks, water, cigarettes, beer, instant noodles, packaged buns. Convenience assortment.
- Same columns PLUS `SlipType, CounterNo, PromoSK` (promo link!), `PKList`.

## This is everything demand forecasting needs
| Need | Column |
|---|---|
| Target (units) | **Qty** |
| Product | StockCode / Barcode / Description |
| Outlet | Location / LocationName |
| Date | DocumentDate (YYYYMMDD) + DocumentTime |
| Price/revenue | Price, Amount, NetAmount, Discount |
| Promo link | PromoSK (MCSSalesDetails) |
| Customer | MemberID (joins to loyalty CR_Transactions) |

## Where "Seasons Bakery" sits
- Standalone Seasons Bakery fresh outlets (loyalty codes SBBH, SB50…) are NOT separate POS locations in CMHL_POS_DB.
- BUT Seasons-branded products ARE sold as SKUs across the network:
  SEASONS HAM&CHEESE SANDWICH, SEASONS CHICKEN SANDWICH, SEASONS CHEESE PUFF,
  SEASON CHOCOLATE BUN, SEASONS VANILLA CAKE RUSK.
- Packaged bakery brands also present: Pucci, Koung Mon, Moe, Samudra, Champion.

## Two framings of the use case (decide)
1. **Bakery SKUs across the retail network** (City Mart/Ocean/Express) → buildable NOW with `SalesDetails` + `MCSSalesDetails`. Filter to bakery category/brand, forecast Qty per (outlet, SKU, day).
2. **Standalone Seasons Bakery 100 fresh outlets** → their own POS not in this DB. Need that source (ask data team), OR use loyalty CR_Transactions as outlet-level proxy.

## Other DBs to inspect (not yet opened)
- `CMHL_BI_DB` — likely curated BI marts (may have ready daily aggregates + product/outlet masters).
- `HUB_REPORTING_DB`, `HUB_STAGING_DB` — reporting / raw staging.

## Notes / gotchas
- `DocumentDate` is varchar YYYYMMDD → cast for date math. Min shows 19700101 (some null/garbage dates) → filter `DocumentDate >= '20230101'`.
- 1.16B rows → ALWAYS aggregate server-side (GROUP BY) + filter date+location. Never pull raw.
- Need a **product master** (category, shelf life) + **outlet master** — check CMHL_BI_DB next.
