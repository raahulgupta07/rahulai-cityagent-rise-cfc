# Fabric Data Findings — live test 2026-06-24

## Connection: SUCCESS
- User login (`ActiveDirectoryPassword`) works. MFA off. Logged in as `rahulgupta@cityholdings.com.mm`, db `CityPlatforms`.
- Driver ODBC 18 installed, connector `fabric_user_connector.py` verified end-to-end.

## What `ods` schema exposes
ONE table only: **`ods.CR_Transactions`** = City Rewards loyalty credit ledger (group-wide).

| Metric | Value |
|---|---|
| Rows | 79,989,791 |
| Date span | 2018-02-01 → 2026-06-23 |
| Shops | 720 |
| Brands | 63 |
| Txn types | 15 |
| Accounts | 1,518,457 |

Txn types (top): Topup Compensate (62M), Charge (13M), Charge CreditExpire (3.2M), Topup, Transfer...
Top brands: City Mart Supermarket (27M), Ocean Supercenter (17M), Marketplace (10.5M), ... **Seasons Bakery (4.27M)**.

Columns (47): DayKey, Date Create, Request Number, Staff/Brand/Shop Name, Terminal ID/Group,
Amount (decimal), Account fields, Credit Code, Transaction Type, plus employee HR fields. LoadDate, FileName.

### CRITICAL: no product grain
No SKU / product / item / quantity column exists. Only money measure = `Amount`.
→ This is a loyalty points/cash ledger, NOT POS product sales.

## The bakery
`Brand Name = 'Seasons Bakery'`:
- **100 shops** (matches the 50-100 outlet use case)
- 4,265,915 txns, 2018-03-23 → 2026-06-23
- Txn types: Topup Compensate (3.45M = points earned), Charge (816k = customer spend)
- Charge rows carry: Date Create, Shop Name, Terminal ID, Amount, Credit Code (CITYPOINT / CITYCASH)

## Feasibility
CAN model from this data:
- Per-outlet DAILY transaction count = foot-traffic proxy
- Per-outlet DAILY Amount (Charge) = spend/revenue proxy
- Day-of-week, seasonality, holiday, promo-lift (merge loyalty xlsx on date)
- Outlet ranking, trend, anomaly

CANNOT model from this data:
- Per-SKU bakery units (no product column)
- Which product to stock / order qty per item
- Waste / expiry per item

## Decision point
1. **Get POS line-item sales** (SKU + qty + outlet + date) from another warehouse/schema/lakehouse — required for true per-product warehouse-stock forecasting. Ask data team.
2. **OR** scope v1 to outlet-level demand forecasting (daily revenue/traffic per Seasons Bakery outlet) using CR_Transactions now. Useful for staffing, outlet-level procurement envelope, promo ROI.

## Extract template for outlet-level (ready to run)
```sql
SELECT
    CAST([Date Create] AS date)        AS sale_date,
    [Shop Name]                        AS outlet,
    COUNT(*)                           AS txn_count,
    SUM(CASE WHEN [Transaction Type]='Charge' THEN Amount ELSE 0 END) AS charge_amount
FROM ods.CR_Transactions
WHERE [Brand Name]='Seasons Bakery'
GROUP BY CAST([Date Create] AS date), [Shop Name];
```
→ land to data/raw/seasons_outlet_daily.parquet, merge promo calendar, LightGBM quantile (plan.md Stage 2, outlet-level target).
