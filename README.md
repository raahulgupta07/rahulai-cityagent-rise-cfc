# CityAI CFC — Bakery Demand Forecasting

ML demand forecasting for **CityFood Concepts (CFC)** bakery network — forecast daily demand per
(outlet, product) and turn it into smart daily warehouse order quantities that cut both stockouts
and waste. Brands: **Seasons** (85.5% of volume), NBH, Bistro, Gong Cha.

## Status (2026-06-24)
| Phase | State |
|---|---|
| 0 Setup & scope | ✅ done |
| 1 Data extraction | ✅ done — 7.08M-row demand panel + 11 masters, validated |
| 2 EDA & profiling | ✅ done — `reports/demand_profile.md` |
| 3 Feature engineering | ✅ done — `data/features/train.parquet` (8.33M rows, 35 feats) |
| 4 Baselines | ✅ done — floor WMAPE 0.401 (moving_avg_7), `reports/baselines.md` |
| 5 Model (LightGBM quantile) | ✅ done — WMAPE 0.341 (+15% vs floor), `reports/model_lgbm.md` |
| 6 Backtest & eval | ✅ done — walk-forward +16%, P50 −21% cost, `reports/eval.md` |
| 7 Order qty (newsvendor) | ✅ done — order plan + picklist + tradeoff, `reports/order_policy.md` |
| 8 Serving pipeline (self-learning) | ✅ done — retrain/predict/monitor, drift, `reports/drift_monitor.md` |
| 9 Dashboard & handoff | ✅ done — `reports/dashboard.html` + `HANDOFF.md` |

### Results so far
- Baseline floor: moving_avg_7 = WMAPE **0.401** (Class-A 0.349).
- LightGBM P50: WMAPE **0.341 overall (+15%)**, Class-A **0.291 (+17%)**.
- Quantile calibration: P85 cover 85.5%, P95 cover 94.5% (well-calibrated → newsvendor-ready).
- Models saved: `models/lgbm_p50|p85|p95.txt`.
- Backtest (walk-forward, 3 folds, `reports/eval.md`): LGBM 0.341 vs floor 0.405 (+16%), stable
  every fold + every ABC class. P85 cover 85.4%, P95 94.5%.
- Business sim (newsvendor, GM 35%, full spoilage): **LGBM P50 lowest cost — ₭2.94B vs baseline
  ₭3.71B = −21%** over 608k order-days. Finding: thin-margin/perishable → critical ratio 0.35 →
  order near median; P85/P95 cut stockouts but waste cost dominates. Per-product CR = Phase 7.
- Open: Croston for intermittent tail (16% vol), Optuna tuning (push past stretch target 0.321).

### Phase 7 done — order quantity (newsvendor)
`src/order_qty.py` — newsvendor per (branch,product,day): order = demand quantile at CR = Cu/(Cu+Co).
CLI: `build` (order_plan.parquet + `reports/order_policy.md`), `picklist --date` (warehouse make-list
CSV), `sweep` (service-vs-waste dial → `reports/service_tradeoff.md`).
- Picklist e.g. 2026-06-20: 235 products, 33,859 units, ₭138M/day, with #outlets + ₭ value per SKU.
- Sweep: cost-min at ~50% service (₭2.94B); 95% service cuts stockout to 4% but waste cost → ₭10B.
- **Finding:** with FLAT demo econ (GM35%/same-day, every product same CR=0.35) newsvendor ≈ flat P50,
  no gain. Value needs **per-product CR** → edit `data/product_econ.csv` with real margin + shelf-life
  so high-margin/long-shelf SKUs earn safety stock, perishables stay lean.

### Phase 8 done — self-learning pipeline + drift
`src/pipeline.py` — champion/challenger loop. `retrain` (train + versioned registry + promote only if
WMAPE gain ≥1%), `predict --date` (champion → nightly order plan), `monitor` (PSI data drift + WMAPE
accuracy drift → retrain verdict). Registry `models/registry/<ver>/`, pointer `models/champion.json`.
- Champion `v_20260424`: holdout WMAPE **0.319** (beats stretch ≤0.321).
- Drift monitor caught monsoon weather shift (rain/tmax PSI high) but accuracy held (0.310) → loop
  flags data drift while accuracy gate stays the real retrain trigger.

### Phase 9 done — dashboard & handoff
`src/dashboard.py` → `reports/dashboard.html` (self-contained, Chart.js): KPI cards, forecast-vs-actual
trend, accuracy by ABC, service-vs-waste dial, top picklist, drift status. `HANDOFF.md` = runbook
(daily/weekly commands, when to retrain, **how to plug real econ into `data/product_econ.csv`**).
**All 9 build phases complete.** Only production gap = real per-product margin + shelf-life.

## Data source
Microsoft Fabric (user-login connector). Demand fact:
`HUB_REPORTING_DB.edm.CFC_PBID_Sales_Summary` (grain: day × branch × product).
Masters in `HUB_REPORTING_DB.cfc.*`. See `schema_cfc_bakery.md`.

Extracted locally → `data/raw/`:
- `demand_panel.parquet` — 7.08M rows, 2023-01-01→2026-06-23, 84 branches, 3,580 products.
- 11 dim/master parquets (product, branch, warehouse, channel, segment, uom, etc.).
- External signals: `data/external/weather_daily.csv` (3yr, 6 cities), `myanmar_holidays.csv` (festivals).

## Key facts
- Target = `net_units` (Quantity − Refund − Void).
- 71% of volume = "smooth" series → LightGBM. 53% of series intermittent → Croston/SBA.
- 99 products (3%) drive 80% of volume (Class A).
- FG (finished goods) = 99.7% of units.
- Festivals shift demand: public holiday +7%, Thingyan −8% (shops close).

## Model strategy
Segment → bake-off → best (not kitchen-sink ensemble):
1. Route by series type — smooth/erratic → LightGBM; intermittent/lumpy → Croston/SBA.
2. Bake-off in LightGBM universe (naive vs LightGBM vs tuned) on shared rolling-origin folds.
3. Pick single best per segment; blend only if proven (uncorrelated errors + beats both).
4. Production = champion/challenger — live model + shadow candidate, promote only if better.
Score: WMAPE + pinball, volume-weighted (Class-A first).

## Feature matrix
`data/features/train.parquet` — 8.33M rows, 35 features, Class A+B FG (402 products × 84 branches),
daily calendar zero-filled per active series, target col `y`. Leak-safe (lag/rolling shift≥1).
Known: weather 9% null (CSV starts 2023-06-24). Optional fix pending.

## Repo layout
```
PROJECT_PLAN.md            full 11-phase build plan
plan.md                    ML approach
schema_cfc_bakery.md       data model (THE reference)
pos_discovery.md           how the data was found
metadata_CR_Transactions.md  loyalty ledger (out of scope)
data_request_email.md      data-team request draft
slides.html / .pdf         exec deck
CLAUDE.md                  agent instructions
fabric_user_connector.py   Fabric DB access (user login)
fetch_weather.py, build_holidays.py
src/
  extract.py               staged extraction (small→fact, chunked, resumable)
  eda.py                   demand profiling
data/
  raw/   external/   features/   predictions/
reports/
  extract_qc.md  demand_profile.md  figs/
```

## Running
```bash
# extract (per-table approval expected — see CLAUDE.md)
python3 src/extract.py small      # masters
python3 src/extract.py fact       # demand panel (chunked)
# profile
python3 src/eda.py
```

## Connection
User-login (Entra email+password) via ODBC `ActiveDirectoryPassword`. Creds in `.env` (gitignored).
Cross-DB queries work (`HUB_REPORTING_DB.*` from default DB). Landmine: needs `,1433` +
`Connection Timeout=30` in conn string. Occasional 08001 handshake → retry wrapper handles it.

---

## Operator app — "Meridian" (web + api)

Full-stack app on top of the engine (`APP_BUILD_PLAN.md` = build log; `CLAUDE.md` = conventions;
`HANDOFF.md` = prod runbook). SvelteKit 5 + Tailwind (web/) · FastAPI + DuckDB (api/) · **SQLite**
`data/app.db` (uploads/audit/jobs, `deps/db.py`) · parquet forecast data, read-only via DuckDB.

**Audience: Data Science team** — the UI shows the real technical terms (WMAPE, LightGBM quantile
P50/P85/P95, newsvendor, PSI). (Earlier operator-safe "neutralized" labels were dropped when the
Meridian design was adopted.)

**Design:** ported from the CFC Meridian design — dark navy 248px rail, terracotta accent, Manrope +
IBM Plex Mono, white rounded-14 cards. One **Workspace** nav of 8 screens:
Overview · Data Explorer · Model Leaderboard · Model Evidence · Forecast Dashboard · Smart Ordering ·
Monitoring · Deploy & API. (Deploy & API screen matches the design; other screens: skin done,
Meridian layout rebuild in progress.)

### Run — dev
```bash
cd api && AUTH_DISABLED=1 APP_ENV=dev python3 -m uvicorn main:app --port 8811
cd web && API_PROXY=http://127.0.0.1:8811 node_modules/.bin/vite dev --port 8812   # open :8812
```

### Run — production (Docker single-host)
```bash
cp .env.example .env.prod     # set SECRET_KEY, ALLOWED_ORIGINS, ORIGIN, DOMAIN
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
# Caddy (:80/:443) → /api → api (1 worker) · /* → web. Health: <origin>/api/health
```
Prod boot fails closed on a default/missing `SECRET_KEY` or `AUTH_DISABLED=1`. The **api image is
baked** (no code mount) → rebuild the api image to load backend changes:
`docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build api`.

### Tests
```bash
cd api && python3 -m pytest tests/ -q     # routes, stores, upload validation, security posture
```
