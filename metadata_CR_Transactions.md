# Metadata — `ods.CR_Transactions` (City Rewards loyalty ledger)

Profiled live 2026-06-24. Total rows: **79,989,791**. Span 2018-02-01 → 2026-06-23.
Machine-readable: `data/metadata_CR_Transactions.csv`.

## What this table is
City Rewards loyalty **credit ledger** (points + cash) across the City Holdings group.
One row = one loyalty transaction (earn/spend/transfer of CITYPOINT or CITYCASH).
Right-side HR columns (~45% null) = optional **employee enrichment** — populated only when the
account maps to a staff member. Not needed for demand forecasting.

## Column groups

### A. Transaction core (always present)
| Column | Type | Distinct | Null% | Notes |
|---|---|---|---|---|
| CreditLogID | bigint | 77.9M | 0 | row PK (loyalty log id) |
| Request Number | varchar | 79.1M | 0 | unique txn ref |
| Request Number Ref | varchar | 65M | 0.03 | linked/original txn |
| Payment Ref | varchar | 76.4M | 0 | payment reference |
| Date Create | datetime2 | 33.2M | 0 | **event timestamp** (use for daily grain) |
| DayKey | varchar | 2550 | 0 | YYYYMMDD date key (e.g. 20260407) |
| LoadDate | datetime2 | 22k | 0 | ETL load time |
| FileName | varchar | 1213 | 0 | source file |

### B. Location / outlet (the join keys for forecasting)
| Column | Type | Distinct | Null% | Notes |
|---|---|---|---|---|
| Brand Name | varchar | 63 | 0.32 | e.g. **Seasons Bakery** (the bakery) |
| Shop Name | varchar | 727 | 0.32 | **outlet** — 100 for Seasons Bakery |
| Terminal ID | varchar | 12.2M | 0.32 | POS terminal (high cardinality, per-device) |
| Terminal Group | varchar | 622 | 0.32 | terminal cluster |
| Staff Name | varchar | 9244 | 0.32 | cashier |

### C. Measure + txn classification
| Column | Type | Distinct | Null% | Values |
|---|---|---|---|---|
| Amount | decimal | 127k | 0 | currency value (Kyats). Only numeric measure |
| Transaction Type | varchar | 15 | 0 | Topup Compensate(62M), Charge(13M), Charge CreditExpire(3.2M), Topup, Transfer... |
| Credit Code | varchar | 3 | 0 | **CITYPOINT (76.1M), CITYCASH (3.9M)** |
| Request Source | varchar | 3(+null) | 41.6 | CardNotPresent(26M), CardPresent(1.6M), null(33M) |
| Ref1 | varchar | 2.1M | 38.7 | misc ref |

### D. Account (customer) attributes
| Column | Type | Distinct | Null% | Values |
|---|---|---|---|---|
| Account Number | varchar | 1.52M | 0 | customer id (1.5M members) |
| Account Type | varchar | 6 | 0 | Default(70.7M), Family(7M), Non-Member(1.6M), VIP(0.47M), Transfer |
| Account Level | varchar | 4 | 0 | 1(69.5M), 0(10.5M), 2(44k) |
| Account Status | varchar | 4 | 0 | Active(79.8M), Block(175k) |
| Gender | varchar | 11 | 0 | (dirty — 11 distinct, needs clean) |
| Title/First/Last Name | varchar | — | 0.4–8 | PII |
| Identity/Passport/Phone Number | varchar | — | 1.6–4.4 | **PII — do not export raw** |

### E. Employee/HR enrichment (~45% null — IGNORE for forecasting)
EmployeeID, EmployeeName, NRCNumber, DOB, PhoneNumber, EmploymentStatus, JoinDate, Position,
Branch, JobTitle, Grade, Status, CostCentreID/Name, WorkLocation, SectionName, Department, Company.
Present only for staff-linked accounts. Drop for demand model.

## Forecasting-relevant subset
Keep: `Date Create`, `DayKey`, `Brand Name`, `Shop Name`, `Terminal Group`, `Transaction Type`,
`Credit Code`, `Amount`, `Account Type`, `Account Number` (for unique-customer counts).

## Key facts / gotchas
- **No product/SKU/quantity column** — confirmed across all 47. Outlet-level only, not per-item.
- `Date Create` granular to second → cast to date for daily grain; `DayKey` is the ready-made date key.
- `Amount` semantics depend on `Transaction Type`: **Charge = customer spend (demand signal)**;
  Topup/Compensate = points issuance (not spend). Filter to Charge for demand.
- PII present (NRC, passport, phone, names). Aggregate away before landing/training.
- `Gender` dirty (11 distinct) — clean if used.
- Shop Name has 727 distinct vs 720 brand-distinct shops → minor naming dupes; normalize.

## Demand-proxy extract (outlet-daily, Seasons Bakery)
```sql
SELECT
    [DayKey]                                AS day_key,
    CAST([Date Create] AS date)             AS sale_date,
    [Shop Name]                             AS outlet,
    COUNT(*)                                AS txn_count,
    COUNT(DISTINCT [Account Number])        AS unique_customers,
    SUM(CASE WHEN [Transaction Type]='Charge' THEN Amount ELSE 0 END) AS charge_amount,
    SUM(CASE WHEN [Transaction Type]='Charge' THEN 1 ELSE 0 END)      AS charge_count
FROM ods.CR_Transactions
WHERE [Brand Name]='Seasons Bakery'
GROUP BY [DayKey], CAST([Date Create] AS date), [Shop Name];
```
