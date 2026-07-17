# CFC Bakery Data Model — HUB_REPORTING_DB (schemas `cfc` + `edm`)

Discovered + profiled live 2026-06-24. **This is the right dataset for the use case.**
CFC = the bakery/cafe business unit (Seasons Bakery + Gong Cha). Branch codes: SBBAGO, SBIC, GCHD…
All 15 tables readable by `rahulgupta@cityholdings.com.mm`.

---

## ⭐ THE demand fact — `edm.CFC_PBID_Sales_Summary`
Pre-aggregated daily sales at exactly the grain we need.
- **13,389,442 rows**, grain = `DayKey × BranchId × ProductId (× CardType)`.
- **84 branches, 3,790 products, 2022-06-21 → 2026-06-23 (4 years daily).**
- Columns:
  | Col | Type | Meaning |
  |---|---|---|
  | DayKey | varchar | date YYYYMMDD |
  | BranchId | int | outlet → Ref_Branch_Master |
  | ProductId | int | SKU → Ref_Product_Master |
  | CardType | varchar | loyalty card / channel (e.g. "City Rewards Digital") |
  | Note | varchar | annotation |
  | **Quantity** | decimal | **units sold = FORECAST TARGET** |
  | RefundQuantity | decimal | refunded units |
  | VoidQuantity | decimal | voided units |
  | Amount | decimal | gross sales value |
  | Discount | float | discount value |
  | SubTotal | float | net |
  | PriceTotalAfterLoyaltyDiscount | float | post-loyalty net |
  | TransCount | int | # transactions |
  | LoadDate | datetime2 | ETL load |

Net demand per (branch, product, day) = `Quantity - RefundQuantity - VoidQuantity`.

## Other facts (`edm`)
- `CFC_PBID_BranchSales` (86k) — branch×day totals (Quantity, Amount, Discount, TransCount). Fast branch-level baseline.
- `CFC_PBID_SlipDiscount_Summary` (6.7k) — discount fact by product×branch×day.
- `CFC_PBID_BranchSlipDiscount` (5.2k) — branch×day discount totals.
- `CR_PBIM_Active_Point_Member_Count` — monthly active loyalty members by channel/account type.

---

## Dimensions / masters (`cfc`)

### `Ref_Product_Master` (29,515 rows) — SKU master
ProductId, ProductName, ProductCode, OldProductCode, ListPrice, UoM, Factor, Active,
CategoryId/Name + **5-level category hierarchy** CatLvl1..5_Id/Name.
- CatLvl1: **FG** (finished goods, 22.7k), Premix (1.7k), RM (raw material, 788), Semi-FG, MTN, ADM, B2B.
- CatLvl2 includes "Seasons". → filter `CatLvl1_Name='FG'` for sellable bakery goods.

### `Ref_Branch_Master` (98 rows) — outlet master
BranchId, BranchName, BranchCode, CompanyId, Telephone, Address, Segment, CostCenter,
ProfitCenter, PartnerId, **StockInId, StockOutId** (warehouse links), MainBranch, OpeningDate,
TimingInfo, ChannelId, SequenceId.
- 98 outlets ≈ the "50–100" in the use case. Codes: SBBAGO, SBIC, GCHD (Gong Cha), LYDSK…

### `Ref_StockWarehouse_Master` (119 rows) — warehouse / replenishment
WarehouseId, WarehouseName, Code, BranchId, PartnerId, + full replenishment config:
**BuyToResupply, ManufactureToResupply, ManufacturePullId, ReceptionSteps, DeliverySteps,
routes (Reception/Delivery/Crossdock)**, stock-loc ids. → models warehouse→branch supply.

### `Ref_StockLocation_Master` (1,409) — stock locations, 3-level hierarchy, BranchId link.
### `Ref_Uom_Master` (62) — units, conversion Factor, MeasureType.
### `Ref_Partner_Master` (4,918) — partners/suppliers, lat/long, type.
### Dims: `Dim_Channel`(7), `Dim_Company`(1), `Dim_CostCenter`(163), `Dim_ProfitCenter`(85), `Dim_Segment`(9).

---

## Star schema (joins)
```
CFC_PBID_Sales_Summary
   .BranchId   → Ref_Branch_Master.BranchId   → Dim_Segment / Dim_ProfitCenter / Dim_Channel
   .ProductId  → Ref_Product_Master.ProductId  (→ CatLvl1..5, UoM)
Ref_Branch_Master.StockInId/StockOutId → Ref_StockWarehouse_Master → Ref_StockLocation_Master
```

---

## What we can DO with this

### 1. Demand forecasting (the core goal) — buildable NOW
- Target = daily `Quantity` per (BranchId, ProductId). 4 yrs history, 84 branches, 3,790 active SKUs.
- Join product category (CatLvl1=FG) → forecast sellable bakery items only.
- Merge external signals already built: promo calendar, weather (`data/external/weather_daily.csv`),
  Myanmar holidays/festivals (`myanmar_holidays.csv`) — all join on date.
- LightGBM quantile model (plan.md Stage 2) → P50/P85 per item per outlet.

### 2. Warehouse replenishment (the "order from warehouse" part)
- Ref_StockWarehouse_Master + Branch StockIn/StockOut → map each outlet to its supplying warehouse.
- Aggregate item forecasts up to warehouse → daily picklist + procurement envelope.
- Newsvendor order qty (plan.md) using ListPrice (margin) vs spoilage.

### 3. Analytics / insights (immediate, no ML)
- Per-branch, per-category sales trends, day-of-week, seasonality (Thingyan etc).
- Refund/void rate per product (quality / over-order signal).
- Discount effectiveness (Discount vs Quantity lift).
- Top/bottom SKUs per outlet; new-branch ramp (OpeningDate).

---

## Gotchas
- `DayKey` is varchar YYYYMMDD → cast for date math; filter `DayKey >= '20230101'` for clean window.
- 13.4M rows → aggregate server-side; pull the panel, not raw, to `data/raw/`.
- Sales_Summary has 84 branches vs 98 in master → some branches no sales / closed; join, don't assume 1:1.
- Multiple CardType rows per (day,branch,product) → SUM across CardType for total units.
- Quantity is gross → subtract Refund + Void for net demand.
- Category hierarchy: use CatLvl1='FG' to exclude RM/Premix/Semi-FG (inputs, not sold to customers).

## Connection note
Cross-DB query works: `HUB_REPORTING_DB.cfc.*` / `HUB_REPORTING_DB.edm.*` from current `.env`
(default DB CityPlatforms). No re-point needed. Access was always there — just not discovered before.
