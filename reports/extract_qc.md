# Extraction QC Report — 2026-06-24

## Demand fact — `data/raw/demand_panel.parquet`
- Source: `HUB_REPORTING_DB.edm.CFC_PBID_Sales_Summary` (aggregated server-side, chunked by month).
- **7,084,242 rows**, 34.2 MB, 10 columns.
- Grain: DayKey × BranchId × ProductId (CardType collapsed via SUM).
- Columns: DayKey, BranchId, ProductId, gross_units, net_units, refund_units, void_units, amount, discount, txns.
- net_units = Quantity − RefundQuantity − VoidQuantity.

### Quality
| Check | Result |
|---|---|
| Date range | 20230101 → 20260623 (1,270 days, continuous) |
| Branches | 84 |
| Products | 3,580 |
| Nulls | none |
| Orphan branches (fact not in master) | 0 |
| Orphan products (fact not in master) | 0 |
| Negative net_units | 69 rows (0.00%) — refund-heavy days, expected |
| Zero net_units | 378 rows (0.01%) |
| Total net units (all time) | 58,804,247 |
| Total amount (all time) | 207,973,924,791 Ks |

## Master / dim tables (`data/raw/`)
| File | Rows | Cols |
|---|---|---|
| dim_company | 1 | 3 |
| dim_channel | 7 | 6 |
| dim_segment | 9 | 6 |
| dim_uom | 62 | 11 |
| dim_profitcenter | 85 | 6 |
| dim_branch | 98 | 18 |
| dim_warehouse | 119 | 11 |
| dim_costcenter | 163 | 6 |
| dim_stocklocation | 1,409 | 10 |
| dim_partner | 4,918 | 11 |
| dim_product | 29,515 | 15 |

## Notes
- 84 sales branches vs 98 in master → 14 branches have no sales in window (closed/new/non-selling). Join, don't assume 1:1.
- 3,580 sold products vs 29,515 in master → most master SKUs are inactive/non-selling; model on the 3,580 active.
- Month parts kept in `data/raw/_fact_parts/` for resume / incremental.
- Extraction time: masters ~1 min (parallel), fact 42 months ~2 min sequential (6s/month).

## Next
Phase 2 — EDA & demand profiling on demand_panel + masters.
