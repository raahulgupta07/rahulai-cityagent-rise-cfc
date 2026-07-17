# Email — Data Request to Data Team

**Subject: Data request — POS sales data needed for bakery demand forecasting (Seasons Bakery)**

Hi [Data Team],

We're building a demand-forecasting model for Seasons Bakery (100 outlets) to optimize daily warehouse stock orders. I connected to the Fabric warehouse (`CityPlatforms`, schema `ods`) and analyzed what's available. The loyalty data is rich and useful, but it's missing the product-level detail required to forecast stock per item. Summary, insights, and the data request are below.

---

## What I connected to
- Warehouse: `CityPlatforms` → schema `ods` → one table: **`CR_Transactions`** (City Rewards loyalty ledger).
- ~80M rows, 2018 → June 2026, 720 shops, 63 brands, 1.5M loyalty accounts.
- For Seasons Bakery specifically: **100 outlets, 4.27M transactions, history back to 2018**.

## What we understand from this data (insights)
This is loyalty point/cash activity, a strong **proxy for footfall and customer spend** — but not item-level sales.

1. **Strong, steady growth.** Seasons Bakery loyalty spend (Charge amount) has risen every year:
   - 2023: ~269M → 2024: ~463M → 2025: ~627M Ks. 2026 already ~378M by June (on track to beat 2025).
   - Active loyalty customers grew 122k (2023) → 169k (2025).
2. **Clear weekly pattern.** Tuesday is the strongest day by spend (~416M cumulative), Sunday/Saturday also high; Monday is the weakest. → day-of-week is a real demand driver, good for forecasting.
3. **Outlet concentration.** Top outlets (Golden Valley, Myay Ni Gone, Pyay 6.5 miles, Wai Zayan Dar, Junction City) drive a large share of spend → per-outlet models matter; outlets are not interchangeable.
4. **Payment mix.** ~66% of spend value is CITYPOINT (points) vs ~34% CITYCASH — useful for promo/loyalty analysis.
5. **Promo overlay available.** We also have the loyalty Promotions / Buy-X-Get-Y campaign calendar (124 campaigns), plus 3 years of Myanmar weather and festival/holiday data we compiled — all join on date.

## The gap — what's missing
`CR_Transactions` has **no product, SKU, or quantity column** (verified across all 47 columns). It tells us *money/points moved*, not *which products or how many units sold*. We cannot forecast per-item stock from it.

## What we need
To forecast stock per product per outlet, please help us source:

1. **POS sales line items** (the core need) — daily history, ideally 2–3 years:
   - date / timestamp
   - outlet (store code + name)
   - product / SKU code + name
   - **quantity sold**
   - unit price / line amount

2. **Product master** — SKU code, name, category, unit, shelf life, price.

3. **Outlet master** — outlet code, name, city/location, type, size.

4. *(Optional, valuable)* **Warehouse orders / inventory** — daily units ordered & received per outlet (to measure stockout/waste).

## Questions
- Does POS / product-level sales data exist in Fabric in another warehouse, schema, or lakehouse? If so, can my account (`rahulgupta@cityholdings.com.mm`) be granted read access?
- If it lives outside Fabric (POS DB, ERP, file exports), what's the best path for a 2–3 year daily history export?
- A small sample extract (a few days, all columns) would let us confirm the structure immediately.

Thanks,
Rahul
