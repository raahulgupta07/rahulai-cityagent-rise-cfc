# CityAI CFC — Bakery Demand Forecasting: Full Build Plan

Goal: forecast daily demand per (outlet, product) for the CFC bakery network (~98 branches,
3,790 active SKUs), then turn forecasts into daily warehouse order quantities — minimizing both
stockouts (lost sales) and waste (perishable spoilage).

Data source: confirmed. `HUB_REPORTING_DB.edm.CFC_PBID_Sales_Summary` (13.4M rows, 4yr daily,
day×branch×product) + `cfc.*` masters. See `schema_cfc_bakery.md`. External signals already built:
promo calendar (loyalty xlsx), `data/external/weather_daily.csv`, `data/external/myanmar_holidays.csv`.

---

## Tech stack
- **Extract:** Python + pyodbc (`fabric_user_connector.py`, already working, token/user auth).
- **Storage:** Parquet under `data/` (raw → interim → features). DuckDB for local fast joins.
- **Modeling:** LightGBM (quantile) primary; statsforecast (baselines); optional TFT later.
- **Backtest/eval:** custom rolling-origin harness; metrics WMAPE + pinball + business sim.
- **Serving:** batch nightly job → forecasts + order qty to a table/parquet; FastAPI optional.
- **Dashboard:** Streamlit (fast) or push results back to Fabric/Power BI.
- **Orchestration:** cron / Prefect for nightly retrain+predict.

## Repo structure (target)
```
cityaicfcdemandforcasting/
  PROJECT_PLAN.md              # this file
  schema_cfc_bakery.md         # data model
  fabric_user_connector.py     # DB access
  .env (gitignored)
  src/
    extract.py                 # pull panel + masters -> data/raw
    features.py                # build feature matrix -> data/features
    baselines.py               # seasonal-naive, moving avg
    train.py                   # LightGBM quantile, per-horizon
    backtest.py                # rolling-origin eval
    newsvendor.py              # forecast -> order qty
    serve.py                   # nightly predict + order generation
    config.py                  # paths, params, flags
  data/
    raw/  interim/  features/  external/  predictions/
  notebooks/                   # EDA, error analysis
  reports/                     # eval metrics, plots
  models/                      # saved boosters per quantile/horizon
```

---

## PHASE 0 — Setup & scope (0.5 day)
- Confirm modeling universe: branches (filter active, exclude Gong Cha drinks if out of scope),
  product set (`CatLvl1_Name='FG'` finished goods only), date window (2023-01-01 → today).
- Decide forecast horizon: tomorrow (h=1) first; extend to h=1..7 for lead-time ordering.
- Lock target = net units = `Quantity - RefundQuantity - VoidQuantity`, SUM over CardType.
- Deliverable: `config.py` with universe + horizon + paths.

## PHASE 1 — Data extraction (1 day)
- `extract.py`:
  - Pull demand panel server-side aggregated:
    `SELECT DayKey, BranchId, ProductId, SUM(Quantity-RefundQuantity-VoidQuantity) units,
            SUM(Amount) amount, SUM(Discount) disc, SUM(TransCount) txns
     FROM edm.CFC_PBID_Sales_Summary
     WHERE DayKey>='20230101' GROUP BY DayKey,BranchId,ProductId` → `data/raw/demand_panel.parquet`.
  - Pull masters: Ref_Branch_Master, Ref_Product_Master (ProductId,Name,Code,Cat*,UoM,ListPrice),
    Ref_StockWarehouse_Master, branch→warehouse map → `data/raw/*.parquet`.
- Validate: row counts, date continuity, null %, negative/■ units, branch/product coverage.
- Deliverable: clean parquet + a data-quality report in `reports/`.

## PHASE 2 — EDA & demand profiling (1 day)
- Per-branch/category: volume, trend, day-of-week, seasonality (Thingyan/Thadingyut spikes).
- Intermittency analysis: % of (branch,SKU) series that are sparse (many zero days) → route to
  Croston later. Classify series: smooth / erratic / intermittent / lumpy.
- ABC/XYZ: rank SKUs by volume × variability → focus model effort on A/X items.
- Refund/void rates, new-branch ramp (OpeningDate), dead SKUs.
- Deliverable: `notebooks/eda.ipynb` + `reports/demand_profile.md`.

## PHASE 3 — Feature engineering (1–2 days)
- Build daily panel completed to full calendar (fill zero-sales days) per active (branch,SKU).
- Features:
  - **Lags:** units t-1,7,14,28; **rolling** mean/std/min/max 7/14/28d; trend.
  - **Calendar:** dow, day-of-month, month, week, is_weekend, payday.
  - **Holidays/festivals:** join `myanmar_holidays.csv` — is_public_holiday, festival flags,
    Thingyan window, days-to/from major festival.
  - **Weather:** join `weather_daily.csv` by branch→city — rain_mm, is_rainy, is_heavy_rain,
    tmax, is_hot, lags + next-day forecast at order time.
  - **Promo:** explode loyalty campaign calendar → promo_active, promo_type, discount intensity.
  - **Product:** CatLvl1-3, UoM, ListPrice, shelf-life proxy. **Branch:** segment, channel, size proxy.
  - **Price/discount:** own Discount ratio.
- No leakage: only features known at order-cutoff time.
- Deliverable: `features.py` → `data/features/train.parquet`.

## PHASE 4 — Baselines (0.5 day)
- Seasonal-naive (same weekday last week, smoothed), 28-day moving average, last-year-same-day.
- Establish WMAPE floor per series class. **Model must beat these.**
- Deliverable: `baselines.py` + baseline metrics in `reports/`.

## PHASE 5 — Model (2–3 days)
- **Primary:** LightGBM global model, panel data, categorical BranchId/ProductId/Category.
  - Quantile objective → train P50 + P85 (+ P95) for safety stock.
  - Per-horizon models (h=1..7) or recursive.
- **Intermittent SKUs:** Croston / SBA via statsforecast for lumpy series (from Phase 2 class).
- **Cold start:** new branch/SKU → category×region fallback hierarchy.
- Hyperparam tune (Optuna) on rolling-origin folds.
- Deliverable: `train.py`, saved `models/`, feature importance.

## PHASE 6 — Backtest & evaluation (1–2 days)
- Rolling-origin (walk-forward) backtest, NOT random split.
- Metrics: WMAPE, MAE, bias, **pinball loss** (quantile quality), coverage (P85 hit rate).
- **Business sim:** simulate ordering with forecast → stockout rate, waste rate, fill rate, ₭ impact
  vs current/baseline ordering. This is the number that sells the project.
- Error analysis: worst branches/SKUs, festival/weather miss cases.
- Deliverable: `backtest.py` + `reports/eval.md` with $ savings estimate.

## PHASE 7 — Order quantity (newsvendor) (1 day)
- Convert quantile forecast → order qty: `order = P_q forecast + safety`, where critical ratio
  `q = Cu/(Cu+Co)` from per-product margin (ListPrice) vs spoilage cost (shelf life).
- Aggregate branch-SKU forecasts → warehouse picklist (via branch→warehouse map) → procurement.
- Constraints: MOQ, case/UoM rounding, shelf-life caps.
- Deliverable: `newsvendor.py` → `data/predictions/orders_<date>.parquet`.

## PHASE 8 — Serving pipeline (1–2 days)
- `serve.py` nightly: pull latest actuals (incremental watermark) → features → predict →
  order qty → write results (parquet + optionally back to Fabric table / Power BI).
- Monitoring: forecast vs actual drift, data freshness, model staleness → alerts.
- Retrain cadence: weekly full retrain; daily predict.
- Deliverable: scheduled job (cron/Prefect) + run logs.

## PHASE 9 — Dashboard & handoff (1–2 days)
- Streamlit (or Power BI on the results table): per-branch/SKU forecast vs actual, recommended
  order, stockout/waste KPIs, festival/weather overlays, accuracy tracking.
- Docs: runbook, model card, retrain guide.
- Deliverable: dashboard + `reports/model_card.md`.

## PHASE 10 — Iterate (ongoing)
- Add TFT/DeepAR if LightGBM plateaus and cross-series patterns justify.
- Feedback loop from actual orders/waste → recalibrate critical ratios.
- Expand horizon, add price elasticity, promo cannibalization pairs.

---

## Milestones
| M | Deliverable | ~Effort |
|---|---|---|
| M1 | Data extracted + validated (P0-1) | 1.5 d |
| M2 | EDA + features (P2-3) | 2-3 d |
| M3 | Baseline beaten by LightGBM, backtested (P4-6) | 4-5 d |
| M4 | Order qty + nightly pipeline (P7-8) | 2-3 d |
| M5 | Dashboard + handoff (P9) | 1-2 d |
| **Total MVP** | end-to-end working forecaster | **~2-3 weeks** |

## Success metrics
- Beat seasonal-naive WMAPE by ≥20% on A/X SKUs.
- P85 coverage 80-90% (calibrated).
- Simulated: stockout ↓ and waste ↓ vs current ordering, with ₭ savings quantified.

## Risks / mitigations
- **No SKU shelf-life field** → derive proxy from category; ask data team for shelf-life master.
- **Intermittent demand** → Croston path, don't force GBM on zeros.
- **Branch→warehouse map gaps** → validate StockIn/StockOut coverage in Phase 1.
- **Promo data coarse** (campaign-level, not per-SKU/branch) → use as flags; refine if mapping found.
- **Weather city mapping** → build branch→city lookup from Branch_Master.Address.
- **Server load** (13.4M rows) → always server-side aggregate + incremental pulls.

## Immediate next step
Phase 1: run `extract.py` to land `demand_panel.parquet` + masters, validate. Then EDA.
