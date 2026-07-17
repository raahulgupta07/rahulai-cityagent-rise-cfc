# CFC ML on Microsoft Fabric — Phase 1 (notebook port)

Moves the heavy ML (features → train → backtest → gate → predict) **out of the app container** and
**into Fabric**, next to the data. No local RAM ceiling, no ODBC egress. Models tracked in **MLflow**.

The SvelteKit + FastAPI app stays in Docker and just **reads the Lakehouse output tables** (Phase 3).

---

## What's here
- `CFC_ML_Pipeline_Fabric.ipynb` — the pipeline notebook (import this into Fabric).
- `_build_notebook.py` — regenerates the .ipynb (edit cells here, re-run `python3 fabric/_build_notebook.py`).

## Your Fabric map (verified via REST 2026-07-16)
| Workspace | Holds | Role |
|---|---|---|
| **HUB-AI** / `LK_CFC_Sales` | `CFC_Sales_Trans` (19.6M raw), `Ref_ProductMaster` (29,483), `Ref_BranchMaster` (98) | **sales data — stays here, not moved** |
| **MSFB_CH_ML** / `CFC_Lakehouse` | ML workspace (capacity + `CFC_NOTEBK`) | **run the notebook + write outputs here** |

## 1 · Import + shortcut (the no-move step)
1. **MSFB_CH_ML** workspace → **New → Import notebook** → `CFC_ML_Pipeline_Fabric.ipynb`.
2. Open `CFC_Lakehouse` → **New shortcut → OneLake** → workspace **HUB-AI** → lakehouse **LK_CFC_Sales**
   → tick tables **CFC_Sales_Trans, Ref_ProductMaster, Ref_BranchMaster** → Create.
   *(Shortcut = zero-copy. Sales never leaves HUB-AI; the notebook reads it in place.)*
3. In the notebook: **Explorer → add Lakehouse → CFC_Lakehouse** (so `spark.read.table(...)` resolves).

The parameters cell is already set to your real names — `T_SALES=CFC_Sales_Trans` (RAW, aggregated
in-place via Spark `GROUP BY`, `net_units = Quantity − RefundQuantity − VoidQuantity`),
`T_PRODUCT=Ref_ProductMaster`, `T_BRANCH=Ref_BranchMaster`.

## 2 · Manual data (user-provided, from the app)
Small inputs the app collects go to OneLake **`Files/manual/`** (NOT tables) — this is the merge lane:

| File | Cols | Merged on | Effect |
|---|---|---|---|
| `holidays.csv` (required) | `date,is_public_holiday,type,multi_day_event` | date | holiday/festival/Thingyan features |
| `weather.csv` (required) | `date,city,rain_mm,is_rainy,is_heavy_rain,tmax_c,is_hot,humidity_pct` | date,city | weather features |
| `promo.csv` (optional) | `date` | date | `promo_active` (else derived from sales `PromoFlag`) |
| `econ.csv` (optional) | `ProductId,gm,shelf_life_days,salvage_frac` | ProductId | **real critical ratio → newsvendor qty** (the unlock) |

Seed once now: upload the local `data/external/myanmar_holidays.csv` → `holidays.csv` and
`weather_daily.csv` → `weather.csv` into `CFC_Lakehouse/Files/manual/`. Later the app writes them here
via the OneLake API on each user upload (Phase 2).

## 3 · Run
Set the **parameters cell** and Run all:
- `MODE=all` — full experiment (features→train→backtest→gate→predict)
- `MODE=train` / `backtest` / `predict` — single stage
- `CUTOFF` — train window split (train < CUTOFF)

## 4 · Outputs (what the app reads)
| Table | Feeds |
|---|---|
| `cfc_backtest_preds` | Model Evidence / Leaderboard charts (WMAPE, calibration, residuals, by-class/fold) |
| `cfc_order_plan` | Smart Ordering + outlet×SKU Excel |
| `cfc_model_runs` | Leaderboard rows (every run, promoted flag) |
| `cfc_champion` | live-model pointer |
| MLflow `CFC_Demand` / model `CFC_Demand_P50` alias `champion` | lineage + one-click rollback |

## 5 · Schedule
Fabric **Data Pipeline → Notebook activity**, param `MODE=all` weekly + `MODE=predict` daily. Or the
notebook's own **Schedule** button.

---

## Fidelity to the local engine
Same `PARAMS` (quantile, 600 trees, num_leaves 255, lr 0.05), same 3 quantiles P50/P85/P95, same
feature build (lags 1/7/14/28, rmean/rstd 7/14/28, calendar, holidays/Thingyan, weather, promo, ABC),
same champion/challenger gate (`MIN_GAIN` 1%), same newsvendor `q_at`. Ported from
`src/features.py · train.py · backtest.py · pipeline.py`.

## Next phases
- **Phase 2** — app Run-Experiment real-mode calls the Fabric **Job Scheduler REST API**, streams job
  status into the existing CLI-log UI (replaces local subprocess `stream_stage`).
- **Phase 3** — FastAPI `deps/duck.py` reads the Lakehouse **SQL endpoint** (or a scheduled parquet export)
  instead of local parquet. Local subprocess path kept as offline/dev fallback.
