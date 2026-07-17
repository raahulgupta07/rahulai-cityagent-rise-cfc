# CFC Bakery — Data Dictionary (HUB_REPORTING_DB)

Every table: **definition · columns + sample data · summary · links**.
Schemas: `cfc` (masters/dims) · `edm` (facts). Sample rows = real, from extracted parquet
(`data/raw/`). 4 raw discount/branch facts have no local pull yet → marked **[needs Fabric pull]**.

---

## 0. Relationship map (how tables link)

```
                          ┌─ Dim_Channel (ChannelId)
                          ├─ Dim_Segment (SegmentId, by name)
   Ref_Branch_Master ─────┼─ Dim_Company (CompanyId)
     (BranchId) ▲ ▲       ├─ Dim_CostCenter / Dim_ProfitCenter (by name)
               │ │        └─ StockInId/StockOutId ─► Ref_StockWarehouse_Master (WarehouseId)
               │ │                                        │ BranchId, PartnerId, CompanyId
               │ │                                        ▼
               │ │                              Ref_StockLocation_Master (StockLocId, BranchId)
               │ │
   ┌───────────┘ └───────────────┐
   │ BranchId                    │ BranchId
   ▼                             ▼
edm.CFC_PBID_Sales_Summary   edm.CFC_PBID_BranchSales      ← branch×day rollup
   (Day×Branch×Product×CardType)   edm.CFC_PBID_SlipDiscount_Summary  (Branch×Product×day)
   │ ProductId                     edm.CFC_PBID_BranchSlipDiscount    (Branch×day)
   ▼
Ref_Product_Master (ProductId) ── UoM ─► Ref_Uom_Master (UomName)

Ref_Partner_Master (PartnerId) ◄─ Ref_Branch_Master.PartnerId, Ref_StockWarehouse_Master.PartnerId
```

**Star schema in one line:** `Sales_Summary` (the demand fact) is the centre; `BranchId`→branch dim,
`ProductId`→product dim; branch dim fans out to channel/segment/company/cost-centre/profit-centre and
to warehouses (via StockIn/StockOut) → stock locations.

### Foreign-key links (child.col → parent.col)
| From | Column | To |
|---|---|---|
| edm.CFC_PBID_Sales_Summary | BranchId | cfc.Ref_Branch_Master.BranchId |
| edm.CFC_PBID_Sales_Summary | ProductId | cfc.Ref_Product_Master.ProductId |
| edm.CFC_PBID_BranchSales | BranchId | cfc.Ref_Branch_Master.BranchId |
| edm.CFC_PBID_SlipDiscount_Summary | BranchId, ProductId | Branch_Master, Product_Master |
| edm.CFC_PBID_BranchSlipDiscount | BranchId | cfc.Ref_Branch_Master.BranchId |
| cfc.Ref_Branch_Master | CompanyId | cfc.Dim_Company.CompanyId |
| cfc.Ref_Branch_Master | ChannelId | cfc.Dim_Channel.ChannelId |
| cfc.Ref_Branch_Master | Segment (name) | cfc.Dim_Segment.SegmentName |
| cfc.Ref_Branch_Master | CostCenter (name) | cfc.Dim_CostCenter.CostCenterName |
| cfc.Ref_Branch_Master | ProfitCenter (name) | cfc.Dim_ProfitCenter.ProfitCenterName |
| cfc.Ref_Branch_Master | StockInId / StockOutId | cfc.Ref_StockWarehouse_Master.WarehouseId |
| cfc.Ref_Branch_Master | PartnerId | cfc.Ref_Partner_Master.PartnerId |
| cfc.Ref_Product_Master | UoM (name) | cfc.Ref_Uom_Master.UomName |
| cfc.Ref_StockWarehouse_Master | BranchId / PartnerId / CompanyId | Branch / Partner / Company |
| cfc.Ref_StockLocation_Master | BranchId / CompanyId | Branch / Company |

> ⚠ Join, never assume 1:1: **84** branches sell vs **98** in master; **3,580** SKUs sell vs **29,515**
> master. `Sales_Summary` has multiple `CardType` rows per (day,branch,product) → SUM them.

---

## 1. edm.CFC_PBID_Sales_Summary ⭐ — THE demand fact

**Definition:** pre-aggregated daily sales, one row per **DayKey × BranchId × ProductId × CardType**.
13.39M source rows; 84 branches, 3,790 products, 2022-06-21→2026-06-23. Forecast **target =
net = Quantity − RefundQuantity − VoidQuantity**, summed over CardType.

**Columns + sample** *(sample = our GROUP-BY aggregate `demand_panel.parquet`, 7.08M rows, CardType summed)*
| Column | Type | Definition | Sample |
|---|---|---|---|
| DayKey | VARCHAR(8) | calendar day 'YYYYMMDD' (cast to date) | `20230101` |
| BranchId | INT | outlet → Ref_Branch_Master | `1141` |
| ProductId | INT | SKU → Ref_Product_Master | `22955` |
| CardType | NVARCHAR | loyalty card / channel | `City Rewards Digital` |
| Quantity | DECIMAL | gross units sold (target basis) | `14` |
| RefundQuantity | DECIMAL | refunded units | `0` |
| VoidQuantity | DECIMAL | voided units | `0` |
| Amount | DECIMAL | gross sales value (Ks) | `22400` |
| Discount | FLOAT | discount value | `0` |
| SubTotal / PriceTotalAfterLoyaltyDiscount | FLOAT | net / post-loyalty net | — |
| TransCount | INT | # receipts | `8` |
| LoadDate | DATETIME2 | ETL load | — |

**Summary:** the model's input. Grain is fine; net demand is small once aggregated. Gotchas: DayKey is
text (filter ≥ '20230101' drops garbage 1970 dates); 69 negative-net rows = refund-heavy days (real).

---

## 2. edm.CFC_PBID_BranchSales — branch×day rollup  **[needs Fabric pull]**

**Definition:** ~86k rows, branch × day totals (no product grain). Fast branch-level baseline.
**Columns (inferred):** DayKey, BranchId, Quantity, Amount, Discount, TransCount, LoadDate.
**Summary:** sanity-check / aggregate cross-foot for Sales_Summary. Sample pending approved extract.

## 3. edm.CFC_PBID_SlipDiscount_Summary — discount fact  **[needs Fabric pull]**

**Definition:** ~6.7k rows, discount by product × branch × day.
**Columns (inferred):** DayKey, BranchId, ProductId, DiscountAmount, Quantity, TransCount, LoadDate.
**Summary:** promo-lift signal source (discount vs quantity). Sample pending.

## 4. edm.CFC_PBID_BranchSlipDiscount — discount totals  **[needs Fabric pull]**

**Definition:** ~5.2k rows, discount totals branch × day.
**Columns (inferred):** DayKey, BranchId, DiscountAmount, TransCount, LoadDate.
**Summary:** branch-level discount rollup. Sample pending.

---

## 5. cfc.Ref_Branch_Master — outlet master

**Definition:** 98 outlets (84 with sales). Brand via Segment; supply via StockIn/StockOut → warehouse.

| Column | Type | Definition | Sample |
|---|---|---|---|
| BranchId | INT (PK) | outlet id | `1192` |
| BranchName | NVARCHAR | name | `Latt Sone Yuzana Dagon Seikkan Branch` |
| BranchCode | NVARCHAR | code | `LYDSK-DS` |
| V5LocationCode | NVARCHAR | legacy POS code | `LDSK` |
| CompanyId / CompanyName | INT / NVARCHAR | → Dim_Company | `1` / `CityFood Concepts` |
| Segment | NVARCHAR | brand/format (name) | `42 Latt Sone Dagon Seikkan Drink` |
| CostCenter / ProfitCenter | NVARCHAR | accounting (name) | — |
| PartnerId | INT | → Ref_Partner_Master | (null in extract) |
| StockInId / StockOutId | INT | inbound / supplying WH | `903` / `903` |
| MainBranch | INT | parent/flag | — |
| OpeningDate | DATETIME2 | open date | `2025-03-26` |
| TimingInfo | NVARCHAR | trading hours | `7:00 AM to 9:00 PM` |
| ChannelId | INT | → Dim_Channel (~14% null) | `1` |
| Address | NVARCHAR | used to derive city for weather | `No.44/1, Kyun Shwe War St…` |
| Telephone | NVARCHAR | phone | — |

**Summary:** drives geography (Address→city→weather), brand mix, and warehouse routing. Many cols
blank for not-yet-open / closed branches.

---

## 6. cfc.Ref_Product_Master — SKU master

**Definition:** 29,515 SKUs (3,580 sell). 5-level category tree. Filter `CatLvl1_Name='FG'` = sellable.

| Column | Type | Definition | Sample |
|---|---|---|---|
| ProductId | INT (PK) | SKU id | `221211` |
| ProductName | NVARCHAR | name | `American Cheese Cake Slice_Unused_Archived` |
| ProductCode | NVARCHAR | code | `10100107000000003` |
| OldProductCode | NVARCHAR | legacy code | — |
| ListPrice | DECIMAL | selling price (NO cost in source) | `1.0` |
| UoM | NVARCHAR | unit → Ref_Uom_Master | `SLICE` |
| Factor | DECIMAL | UoM conversion | `1.0` |
| Active | BIT | active flag | `False` |
| CategoryId / CategoryName | INT / NVARCHAR | category | `1` / `All` |
| CatLvl1_Name … CatLvl5_Name | NVARCHAR | hierarchy (L1: FG/Premix/RM/…) | `FG` / `Seasons` / … |

**Summary:** product attributes + ABC universe. ListPrice present, **cost/margin absent** — the one
production gap for order-sizing. `_Unused_Archived` names = dead SKUs (Active=False).

---

## 7. cfc.Ref_Partner_Master — partners/suppliers

**Definition:** 4,918 partners with geo + contact. Linked from branch & warehouse PartnerId.

| Column | Type | Definition | Sample |
|---|---|---|---|
| PartnerId | INT (PK) | partner id | `3662` |
| PartnerName / DisplayName | NVARCHAR | name | `Chubb Life Insurance Myanmar Limited` |
| CompanyId | INT | → Dim_Company | — |
| ActiveFlag | BIT | active | `True` |
| Type | NVARCHAR | partner type | `other` |
| PartnerLatitude / PartnerLongitude | DECIMAL | geo | — |
| Email | NVARCHAR | contact | `khin.myo@chubb.com` |
| IsCompany | BIT | company vs person | `True` |
| LoadDate | DATETIME2 | ETL | `2026-06-24` |

**Summary:** reference for supplier/partner geo; mostly out of forecast scope.

---

## 8. cfc.Ref_StockWarehouse_Master — warehouse + replenishment

**Definition:** 119 warehouses with resupply config. Picklist target; maps WH→branch.

| Column | Type | Definition | Sample |
|---|---|---|---|
| WarehouseId | INT (PK) | warehouse id | `135` |
| WarehouseName | NVARCHAR | name | `Season Bakery Star City Thanlyin Branch` |
| Code | NVARCHAR | code | `SBSCT` |
| ActiveFlag | BIT | active | `False` |
| CompanyId / PartnerId / BranchId | INT | → Company / Partner / Branch | `1` / `1` / `1189` |
| BuyToResupply | BIT | replenish by purchase | `True` |
| ManufactureToResupply | BIT | replenish by production | `True` |
| ManuTypeId | INT | manufacture type | `1387` |
| Sequence | INT | order | `10` |

**Summary:** warehouse→branch supply graph for rolling picklist up to the supplying WH.
Source also has route/reception/delivery-step cols (not extracted).

---

## 9. cfc.Ref_StockLocation_Master — stock locations

**Definition:** 1,409 locations, 3-level hierarchy, BranchId link.

| Column | Type | Definition | Sample |
|---|---|---|---|
| StockLocId | INT (PK) | location id | `1203` |
| StockLocName | NVARCHAR | name | `SBJN` |
| ParentPathName | NVARCHAR | hierarchy path | `SBJN` |
| ActiveFlag | BIT | active | `False` |
| Usage | NVARCHAR | usage type | `internal` |
| BranchId / CompanyId | INT | → Branch / Company | (null) / `1` |
| StockLocLvl1..3_Name | NVARCHAR | hierarchy levels | `SBJN` / — / — |

**Summary:** physical stock layout; downstream of warehouse, mostly out of forecast scope.

---

## 10. cfc.Ref_Uom_Master — units of measure

**Definition:** 62 units + conversion factors.

| Column | Type | Definition | Sample |
|---|---|---|---|
| UomId | INT (PK) | unit id | `3` |
| UomName | NVARCHAR | name (→ Product.UoM) | `Days` |
| CategoryId | INT | UoM category | `3` |
| Factor | DECIMAL | conversion to base | `1.0` |
| Rounding | DECIMAL | rounding step | `0.01` |
| ActiveFlag | BIT | active | `True` |
| UomType | NVARCHAR | reference/bigger/smaller | `reference` |
| MeasureType | NVARCHAR | measure class | — |

**Summary:** normalises product units (SLICE, PCS, Days…). Join via name to product.

---

## 11. cfc.Dim_Channel — sales channel (7 rows)

**Definition:** channel/brand lookup for branches.

| Column | Type | Definition | Sample |
|---|---|---|---|
| ChannelId | INT (PK) | channel id | `2` |
| ChannelName | NVARCHAR | name | `Gong Cha` |
| ChannelCode | NVARCHAR | code | `GC` |
| CreateDate / WriteDate / LoadDate | DATETIME2 | audit | `2025-03-24` |

**Summary:** small lookup (LS, Gong Cha, Seasons…). Joins to Branch.ChannelId.

## 12. cfc.Dim_Company — company (1 row)

| Column | Type | Definition | Sample |
|---|---|---|---|
| CompanyId | INT (PK) | id | `1` |
| CompanyName | NVARCHAR | name | `CityFood Concepts` |
| LoadDate | DATETIME2 | ETL | `2026-06-24` |

**Summary:** single operating company (CFC). Top of the org hierarchy.

## 13. cfc.Dim_Segment — brand/format segment (9 rows)

| Column | Type | Definition | Sample |
|---|---|---|---|
| SegmentId | INT (PK) | id | `574` |
| SegmentName | NVARCHAR | name (codes `40/41/42…`) | `40` |
| Description | NVARCHAR | desc | `40` |
| CreateDate / WriteDate / LoadDate | DATETIME2 | audit | `2024-04-28` |

**Summary:** segments are coded numbers; Branch.Segment carries a longer descriptive string → match by
prefix/name, not id.

## 14. cfc.Dim_CostCenter — cost centre (163 rows)

| Column | Type | Definition | Sample |
|---|---|---|---|
| CostCenterId | INT (PK) | id | `1137` |
| CostCenterName | NVARCHAR | code | `4000081` |
| Description | NVARCHAR | branch name | `Seasons Bakery Mingalar Taung Nyunt` |
| CreateDate / WriteDate / LoadDate | DATETIME2 | audit | `2025-02-25` |

**Summary:** accounting cost centre per branch. Description ≈ branch name.

## 15. cfc.Dim_ProfitCenter — profit centre (85 rows)

| Column | Type | Definition | Sample |
|---|---|---|---|
| ProfitCenterId | INT (PK) | id | `570` |
| ProfitCenterName | NVARCHAR | code | `100003` |
| Description | NVARCHAR | location | `Junction-8` |
| CreateDate / WriteDate / LoadDate | DATETIME2 | audit | `2024-04-28` |

**Summary:** accounting profit centre (by location/mall). Links to Branch by name.

---

### Coverage note
Samples for tables 1, 5–15 = real extracted rows. Tables 2–4 (BranchSales,
SlipDiscount_Summary, BranchSlipDiscount) = definitions only; run
`python3 fabric_user_connector.py profile edm.<Table>` (per-table approval) to fill real samples.
