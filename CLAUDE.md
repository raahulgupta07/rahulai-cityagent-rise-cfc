# CLAUDE.md — CityAI CFC Bakery Demand Forecasting

Project goal: ML demand forecasting for CFC (CityFood Concepts) bakery — forecast daily demand
per (outlet, product), convert to daily warehouse order quantities. Cut stockouts AND waste.

## CRITICAL working rules
- **Per-table extraction approval.** When extracting ANY table from Fabric, ask the user's explicit
  approval BEFORE each individual table. Never batch-pull. Run smallest→largest. (User preference.)
- **Read-only on Fabric.** Aggregate server-side (GROUP BY); never pull raw rows from billion-row
  POS tables. Demand fact is already small once aggregated.
- **Data may leave Fabric** onto local disk (confirmed OK) → model locally on parquet.
- **Secrets:** creds live in `.env` (gitignored). Never hardcode/echo the password. Rotate advised
  (was pasted in chat).

## Data source (Microsoft Fabric, user login)
- Connector: `fabric_user_connector.py` — ODBC `Authentication=ActiveDirectoryPassword`, user
  rahulgupta@cityholdings.com.mm. Works. MFA off.
- Endpoint has 6 DBs. We use **`HUB_REPORTING_DB`**, schemas `cfc` (masters) + `edm` (facts).
- Demand fact: `edm.CFC_PBID_Sales_Summary` — grain DayKey × BranchId × ProductId, 13.4M rows,
  2022→2026. Columns incl Quantity, RefundQuantity, VoidQuantity, Amount, Discount, TransCount, CardType.
- Cross-DB query works via 3-part name from default DB (CityPlatforms). No re-point needed.
- LANDMINE: conn string needs explicit `,1433` + `Connection Timeout=30` or 08001/(26) handshake
  error. Occasional 08001 mid-run → use the rq() retry+backoff wrapper.
- Out of scope: `CityPlatforms.ods.CR_Transactions` (loyalty ledger, no SKU), raw POS
  `CMHL_POS_DB` (1.16B, different business unit).

## Modeling decisions (locked)
- Target = `net_units` = Quantity − RefundQuantity − VoidQuantity, SUM over CardType.
- Universe: FG products (CatLvl1_Name='FG'), active branches (84 with sales), date ≥ 2023-01-01.
- 71% of volume = smooth series → LightGBM quantile (P50/P85). Intermittent/lumpy tail → Croston/SBA.
- Focus accuracy on Class-A (99 products = 80% volume).
- Order qty via newsvendor (critical ratio from margin vs spoilage). Aggregate to warehouse picklist.

## Model strategy (locked) — segment → bake-off → best, not kitchen-sink ensemble
1. **Route by series type** (mandatory): smooth/erratic → LightGBM; intermittent/lumpy → Croston/SBA.
   One model can't serve both. This is routing, not ensembling.
2. **Bake-off within LightGBM universe**: seasonal-naive (floor) vs LightGBM global quantile vs
   Optuna-tuned (vs per-channel if channels diverge). Score on SAME rolling-origin folds.
3. **Pick single best per segment.** Blend ONLY if two models both good + errors uncorrelated +
   blend beats both on backtest. Never merge for its own sake (complexity/drift tax).
4. **Production = champion/challenger**: live model + shadow-scored candidate; promote only if better.
   This IS the self-learning loop — answers "one or many?" automatically over time.
- Score metric: WMAPE + pinball, volume-weighted (Class-A weighted highest).

## Results (Phases 4-5 done)
- Baseline floor (`reports/baselines.md`): moving_avg_7 WMAPE 0.401 overall, Class-A 0.349.
  (seasonal_naive_7 worst at 0.528 — recent level beats same-weekday here.)
- LightGBM quantile (`reports/model_lgbm.md`, `src/train.py`, models/lgbm_p50|p85|p95.txt):
  P50 WMAPE 0.341 overall (+15% vs floor), Class-A 0.291 (+17%). Train<2026-04, test 2026-04..06.
  Calibration excellent: P85 cover 85.5%, P95 cover 94.5%. P50 bias −0.42.
  Top features: ProductId, BranchId, rmean_28, lag_1, rstd_28, rolling stats, month.
- OPEN: Croston/SBA for intermittent tail (16% vol) not built; Optuna tuning to pass stretch ≤0.321.

## Backtest + business sim (Phase 6 done)
- `src/backtest.py` → `reports/eval.md`, `data/predictions/backtest_preds.parquet`. Rolling-origin
  expanding window, 3 monthly folds (2026-04/-05/-06), LGBM retrained per fold (no leak), 608k test rows.
- Walk-forward LGBM P50 WMAPE 0.341 vs floor 0.405 = +16%; stable every fold (+23/+10/+12%) + class
  (A 0.291, B 0.456, C 0.640). Calibration P85 85.4% / P95 94.5%.
- Newsvendor sim (GM=35%, full spoilage, Cu=price·GM / Co=price·(1−GM)): **P50 lowest cost ₭2.94B vs
  baseline ₭3.71B = −21%**. KEY: thin margin + full spoilage → critical ratio 0.35 < 0.5 → order
  near/below median. P85/P95 slash stockouts but waste cost dominates → net worse. So Phase 7 must use
  **per-product critical ratio** (real GM + real shelf-life/spoilage), not a flat safety quantile.
- LightGBM trains ~5.5 min on this machine (8.3M rows, 3 quantiles). Use categorical_feature for
  BranchId/ProductId/dow/etc (18 cats) — big signal.

## Order quantity — Phase 7 (DONE)
- `src/order_qty.py`: newsvendor per (branch,product,day). CR=Cu/(Cu+Co), Cu=price·GM,
  Co=(price·(1−GM)−salvage)·spoil_frac (spoil_frac=1/shelf_life_days). order_qty = demand quantile
  @ CR, piecewise-interp from P50/P85/P95 (q_at: cr<.5→p50·cr/.5, then linear thru anchors, ≥.95 cap).
- CLI: `build` → data/predictions/order_plan.parquet + reports/order_policy.md;
  `picklist --date YYYY-MM-DD` → data/predictions/picklist_<date>.csv (joins dim_product names, sorts
  by units, #outlets + ₭value); `sweep` → reports/service_tradeoff.md (service-vs-waste dial).
- ECON table `data/product_econ.csv` (auto-stubbed DEMO: GM35%, shelf_life 1d, salvage 0). EDIT with
  real per-product margin+shelf-life for prod numbers. spoil_frac=1/shelf_life → long-shelf SKUs lower Co.
- RESULT (demo econ): picklist 2026-06-20 = 235 prods/33,859 units/₭138M. Sweep cost-min ~P50 (₭2.94B);
  95% service → stockout 4% but waste→₭10B. **KEY: uniform CR=0.35 → newsvendor≈flat P50, NO gain.
  Newsvendor only pays once CR varies per product (real margin+shelf-life). That's the unlock, not code.**

## Self-learning pipeline — Phase 8 (DONE)
- `src/pipeline.py` champion/challenger. CLI: `retrain [--cutoff]`, `predict --date`, `monitor [--ref-cutoff]`.
- retrain: train P50/P85/P95 on <cutoff (default holdout=last 60d), save models/registry/<ver>/{*.txt,meta.json},
  promote to models/champion.json ONLY if WMAPE gain ≥ MIN_GAIN(1%); else stays challenger.
- predict: load champion booster, forecast date, run order_qty.econ_table+q_at → data/predictions/order_plan_<date>.parquet.
- monitor: PSI per feature (warn>0.20) + champion recent-WMAPE vs holdout (warn>+10%) → reports/drift_monitor.md verdict.
  run log models/pipeline_log.jsonl.
- RESULT: champion v_20260424 holdout WMAPE 0.319 (beats stretch ≤0.321!). Monitor caught monsoon weather
  drift (rain/tmax PSI 2.3/1.6) but accuracy held (recent 0.310) → data-drift flags, accuracy gate is true
  trigger. predict 2026-06-20: 6,354 series→33,789 u (lean vs demand 49,452, demo-econ CR0.35).
- NOTE: meta.json stores feats+cats so predict reuses exact training schema. econ_table imported from order_qty.

## Dashboard & handoff — Phase 9 (DONE) — ALL 9 PHASES COMPLETE
- `src/dashboard.py` → reports/dashboard.html (self-contained, Chart.js CDN). Computes all numbers LIVE
  from backtest_preds + order_plan + champion.json (no hardcode): KPI cards, forecast-vs-actual daily
  trend, accuracy-by-ABC bars, service-vs-waste dual-axis, top-15 picklist (joins dim_product names),
  drift badge. Re-run after pipeline changes. `open reports/dashboard.html`.
- `HANDOFF.md` = runbook: daily predict+picklist, weekly retrain, monitor, when-to-retrain rule
  (accuracy gate not weather alone), and THE production step: edit data/product_econ.csv with real
  gm/shelf_life_days/salvage_frac then re-run order_qty build + pipeline predict (no code change).
- System E2E proven: extract→features→train→backtest→order→picklist→nightly predict→drift→retrain.
  Only remaining gap = real per-product economics. Backlog: Croston tail, Optuna, branch→WH routing.

## Feature matrix (Phase 3 done)
- `data/features/train.parquet` — 8.33M rows, 35 features, Class A+B FG (402 products × 84 branches),
  2023-01-29→2026-06-23, daily calendar zero-filled per active series. Target col = `y`.
- Leak-safe: all lag/rolling shift(≥1). Groups: lags 1/7/14/28, rolling mean/std 7/14/28, rmax_28,
  dow_mean_28, calendar, holidays/festivals/thingyan, promo_active, weather (branch→city), product/branch attrs.
- Known null: weather 9% (CSV starts 2023-06-24, demand starts 2023-01-29) — LightGBM-safe.
  Optional fix: extend weather to Jan-2023 + fill branch ChannelId (14% null) from BranchCode prefix.

## Gotchas from the data
- 84 sales branches vs 98 master; 3,580 sold vs 29,515 master SKUs → join, don't assume 1:1.
- DayKey is varchar YYYYMMDD → cast; filter ≥ '20230101' (drops garbage 1970 dates).
- Median series span only 32 days; 52k series <90 days → heavy churn → cold-start + zero-fill care.
- Festivals: public holiday +7%, Thingyan −8% (shops close — dip not spike).

## Env / tooling
- Python 3.9, pandas 2.1, pyodbc + ODBC Driver 18 (brew msodbcsql18), lightgbm/statsforecast TBD.
- External signals built: `data/external/weather_daily.csv`, `myanmar_holidays.csv`.

## Operator app — "Meridian" (`web/` + `api/`) — built + prod-ready, branch `feature/prod-ready`
Full-stack app on the engine. Build log = `APP_BUILD_PLAN.md`. Reuses `src/*.py` engine UNTOUCHED.
Stack: SvelteKit 5 (runes) + Tailwind (web/) · FastAPI + DuckDB + pyodbc (api/) · parquet (forecast,
read-only via DuckDB) · **SQLite** `data/app.db` (uploads/audit/jobs/scheduler, `deps/db.py`, all
graceful). NO Postgres (removed — overkill single-node).

**AUDIENCE = Data Science team → UI SHOWS technical terms** (WMAPE, LightGBM quantile P50/P85/P95,
newsvendor, PSI). The earlier operator-safe "neutralization" rule was REVERSED when the **Meridian
design** was adopted (user chose full-match). `_neutralise()`/`results.py` still exist but are no longer
a hard gate; `test_neutralize` was removed. Design: dark navy 248px rail + terracotta accent + Manrope/
IBM Plex Mono + white rounded-14 cards; ONE `Workspace` nav of 8 screens (Overview·Data Explorer·Model
Leaderboard·Model Evidence·Forecast Dashboard·Smart Ordering·Monitoring·Deploy & API). Skin applied to
all; **Deploy & API screen rebuilt to the design 1:1** (`/deploy/versions`+`/api-sample`); other 6
screen layouts still being rebuilt to Meridian structure.

**LOCAL DEV RUN** (empty ports; api first):
```
cd api && AUTH_DISABLED=1 APP_ENV=dev python -m uvicorn main:app --host 127.0.0.1 --port 8811
cd web && API_PROXY=http://127.0.0.1:8811 node_modules/.bin/vite dev --port 8812 --host 127.0.0.1
```
Open http://localhost:8812 . api health `/health` (deep: checks DuckDB spine). uvicorn NO reload →
RESTART to load py changes. vite proxy strips `/api` (client `/api/x` → backend `/x`).
Override SQLite path with `APP_DB_PATH` (tests/dev use /tmp).

**PROD deploy (Docker single-host):** `cp .env.example .env.prod` (fill SECRET_KEY/ALLOWED_ORIGINS/
ORIGIN/DOMAIN) → `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`.
Caddy front proxy splits `/api`→api (strips prefix, SSE `flush_interval -1`, auto-TLS) + `/*`→web.
**Prod boot FAILS CLOSED** if `SECRET_KEY` unset/default or `AUTH_DISABLED=1` (raises in startup,
port never opens). CORS denies cross-origin unless `ALLOWED_ORIGINS` set. **api runs ONE worker** —
heavy-lock + job registry are in-process (`deps/jobs.py` `threading.Lock`); more workers = concurrent
trainings. Multi-node would need a Redis/shared lock first. api image is self-contained (bakes `src/`
engine + ML deps via `requirements-engine.txt`); `.dockerignore` keeps the root build context lean.
Tests: `cd api && python3 -m pytest tests/ -q`.
**★★★PROD API IS BAKED** (compose mounts NO ./api) → backend edits need an image rebuild:
`docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build api` (a plain `restart`
serves stale code → new endpoints 404). Web edits likewise need `--build web`. Local HTTP deploy uses
`DOMAIN=:80` + `HTTP_PORT=8080` → http://localhost:8080. ★rtk mangles host `curl` (truncates ~596B);
verify served HTML via `docker exec <caddy> wget -qO- http://localhost:80/…` instead.

**Conventions (MUST follow — enable parallel edits, see `WAVE0.md`):**
- api routers SELF-REGISTER (`routes/__init__.py` scans `routes/<x>.py` for a `router`). NEVER edit main.py to add a feature.
- nav is DATA (`web/src/lib/nav/registry.ts`, append one line).
- `api/deps/duck.py` = DuckDB spine (parquet views); extra parquet views → OWN deps file, never edit duck.py.
- Model/method names ARE shown now (DS-team Meridian UI). `_neutralise()` in `analysis.py` still runs on
  the older Analysis endpoint but is NOT a hard rule anymore — new DS screens surface raw WMAPE/P50/85/95/
  LightGBM/newsvendor directly (e.g. `/deploy/versions`). Add raw technical fields as screens are rebuilt.
- SSE via `sse_starlette.EventSourceResponse` — it AUTO-wraps yielded strings as `data:`; yield RAW json,
  NEVER pre-prefix `data:` (double-prefix = `JSON.parse` throws → Autopilot log empty/stuck).
- Heavy pipeline stages guarded: dry-run by default, `guard=false`/real run holds non-reentrant heavy-lock
  (`api/deps/jobs.py`, one heavy run at a time). Real runs use `python -u` (unbuffered) else log looks frozen.

**Run Experiment (full-pipeline live run)** — `GET /experiments/run` (SSE, self-registered on the
experiments router) chains the WHOLE pipeline as ONE stream of **structured JSON events**
(`experiment_start · stage_start · log · progress · metric · stage_done · gate · done · error`).
Service = `api/services/experiment_run.py`. Chain: extract→sync→features→train→backtest→gate→order→
predict→monitor. Two modes: `sim=true` (default) = scripted rehearsal (no creds/train, ~monthly-batch
+ per-quantile-iter + per-fold animation, `speed` 1-8×); `sim=false` = real via `runner.stream_stage`
(guard_run=False) — Fabric monthly-batch extract + LightGBM train (~12 min). A coarse
`jobs.try_acquire_experiment()` lock (distinct from `_heavy_lock`) stops a 2nd full run interleaving.
Sales extract is MONTHLY-BATCHED + server-aggregated + incremental (`src/extract.py` `_pull_range`),
reflected in the sim log. UI = `web/src/routes/experiments/run/+page.svelte` (nav "Run Experiment" +
Leaderboard "New experiment" button): config → live **stage stepper** + dark **CLI log pane**
(mono, per-level color, source col, rows/secs, auto-scroll, blinking cursor) + **live metric cards** +
**training progress bar/animation** + **gate banner** → on `done` deep-links to `/leaderboard/{version}`
evidence + outlet×SKU xlsx export. Client: `experimentsApi.runStreamUrl(opts)` → `EventSource`.
★libgomp1 IS in the api Dockerfile (LightGBM OpenMP runtime) — real train/backtest/evidence break without it.

**Routers (17)**: sources (2-lane provenance), data (template/upload/validate/accept), demand, order,
experiments (leaderboard/compare/rerun/promote), agent (Autopilot orchestrator, OpenRouter-only), analysis
(14 sections from report .md, neutralised), deploy (drift-over-time + self-retrain), eda (LIVE DuckDB),
pipeline (SSE runner + job history), results, learning, schema, insights, settings, schedule.

**UI system (world-class polish pass)**: `web/src/lib/Icon.svelte` = SVG icon set (Lucide-style, 24
viewBox, `name`/`size`/`class`/`label`; label→role=img else aria-hidden). NO emoji/dingbat glyphs as icons
— use `<Icon name=".." class="w-4 h-4" />` (numeric trend arrows ↑↓→ stay as typography). `web/src/app.css`
= a11y base (focus-visible rings, cursor-pointer, prefers-reduced-motion) + button system: `.btn`/`.btn-primary`
/`.btn-teal`/`.btn-ghost`/`.btn-subtle`/`.btn-warn`/`.btn-sm` (38px min touch, 32 sm), `.pill*`, `.card`/`.card-link`.
Skin tokens in `tailwind.config.ts`: blue `#2E6BE6` + teal `#0AA99B`, dark navy rail, mono+sans.
node_modules platform-mismatched → if `vite build` breaks on esbuild host/binary: `rm -rf node_modules/esbuild
&& npm install esbuild@0.21.5 --no-save` (docker build clean regardless).

**LANDMINES**: per-WH picklist falls back network-wide (`dim_branch.StockOutId` ≠ `dim_warehouse.WarehouseId`,
wrong join key — needs StockLocation route). Auth default secret + `AUTH_DISABLED=1` bypass → set SECRET_KEY +
`AUTH_DISABLED=0` + `APP_ENV=production` in prod (startup logs SECURITY errors). `extract_fact` incremental
merge only tested locally (real DB pull needs Fabric creds).

## ML → Microsoft Fabric (Phases 1 + 2 + 3 DONE — `fabric/` + `api/deps/fabric.py` + `fabric_jobs.py`)
Heavy ML moved OUT of the app container INTO Fabric (compute next to Lakehouse data; in-container train OOMs).
**Full workspace/table map + REST recipe = memory `reference_cfc_fabric_workspaces.md`.** Run ML in **HUB-AI**
workspace; sales stays native in Lakehouse **`LK_CFC_Sales`** (`CFC_Sales_Trans` 19.6M RAW + `Ref_Product/BranchMaster`).

**Phase 1 — notebook (`fabric/CFC_ML_Pipeline_Fabric.ipynb`, built by `_build_notebook.py`):** faithful port of
`src/features+train+backtest+pipeline`. `MODE` = features|train|backtest|predict|monitor|tune|auto|all. Aggregates
raw sales IN-place (Spark GROUP BY, `net_units=Quantity-Refund-Void`, COALESCE nulls), builds features, LightGBM
P50/85/95, walk-forward backtest, champion/challenger gate, newsvendor predict, PSI drift monitor, Optuna tune,
auto drift-loop. MLflow (`CFC_Demand`/`CFC_Demand_P50` alias `champion`) + writes `cfc_features`/`cfc_backtest_preds`/
`cfc_order_plan`/`cfc_model_runs`/`cfc_champion`/`cfc_drift`/`cfc_best_params` to `LK_CFC_Sales/dbo`. Manual data
(holidays/weather/promo/econ) merged from `Files/manual/*.csv`. **ALL 7 STAGES VERIFIED headless via Fabric Job
API** — champion `v_20260401_0416` WMAPE 0.359. Notebook `id e9815e01-…`, pre-attached to LK_CFC_Sales. ★★★headless
jobs give NO cell error → error-capture cell writes traceback to `Files/errors/last_error.txt`; ★lightgbm via
subprocess pip NOT `%pip`; ★verify writes via OneLake `Tables/dbo` listing (SQL endpoint sync lags min).

**Phase 3 — app reads Fabric LIVE (`api/deps/fabric.py`, flag `USE_FABRIC=1`):** pyodbc→`LK_CFC_Sales` SQL endpoint
(ActiveDirectoryPassword, ODBC Driver 18). `routes/experiments.py` leaderboard→`cfc_model_runs`+`cfc_champion`,
evidence→all charts computed live from `cfc_backtest_preds` (T-SQL) — BOTH fall back to local parquet. Env in
`.env.prod`: `USE_FABRIC`/`FABRIC_SQL_ENDPOINT`/`FABRIC_SQL_DB=LK_CFC_Sales`/`FABRIC_SCHEMA=dbo`/`FABRIC_USER`/`FABRIC_PASSWORD`.
VERIFIED live :8080 (champion 0.359, evidence P85 84.2/folds 0.393,0.325). ★★★api Dockerfile MUST pin
`FROM python:3.11-slim-bookworm` — trixie's apt (sqv) rejects Microsoft's SHA1 ODBC repo key → `msodbcsql18` fails.

**Phase 2 — app triggers Fabric + human approval gate (`api/deps/fabric_jobs.py`):** app→Fabric notebook trigger via
Job REST (`POST items/{nb}/jobs/instances?jobType=RunNotebook`, ROPC token, poll `Location`). Notebook now stops
auto-promote → `gate_and_log()` registers a **CHALLENGER** (promoted=False) unless bootstrap or `AUTO_PROMOTE`;
new `MODE=promote`+`PROMOTE_VERSION` sets MLflow `champion` alias + writes `cfc_champion` (human-approved); `train()`
writes `cfc_feature_importance`. App: `POST /experiments/{v}/promote` fires the Fabric promote job (returns `job_id`,
local-file fallback), `POST /{v}/reject`, `GET /experiments/jobs/{id}` polls. UI: Leaderboard **challenger-vs-champion
approval banner** (Approve & promote / Reject + live job status) + Evidence page same; evidence feature-importance now
reads `cfc_feature_importance`. Env: `FABRIC_WORKSPACE_ID` (HUB-AI `6d85b94e-…`) + `FABRIC_NOTEBOOK_ID` (`e9815e01-…`).

**PENDING:** wire Ordering (`cfc_order_plan`) + Monitoring (`cfc_drift`) Fabric reads into the app (order export still
reads local parquet — 404s under Fabric-only); schedule daily `predict`/weekly `auto` Data Pipelines. Regenerate
notebook: `python3 fabric/_build_notebook.py`. ★api image needs `pyarrow`+`pandas` (in `requirements-engine.txt`).

**Phase 4 — UX/trust layer (DONE 2026-07-16, 3 parallel subagents web/api/fabric, baked :8080):**
- **Explain-forecast** (`api/routes/explain.py` + `services/llm.explain`, OpenRouter-only): `POST /explain`
  {version?,branch?,product?,date?,context?} → plain-language "why this number". Model = env `EXPLAIN_MODEL`
  default `z-ai/glm-4.6` (GLM latest); fallback chain GLM→haiku(`AGENT_MODEL`)→deterministic template. Grounds
  on Fabric (champion acc, units-off, top-5 drivers from `cfc_feature_importance`) else local backtest parquet.
  ★`_humanize()` maps raw feature names (rmean_14/lag_7…) → plain phrases so even the OFFLINE template never
  leaks internals. UI = `web/src/lib/ExplainButton.svelte` on `/network` + `/accuracy`.
- **Accuracy screen** (`api/routes/accuracy.py` + `web/src/routes/accuracy`): `GET /accuracy/daily?days=N`
  + `/accuracy/summary`. Daily pred-vs-actual, grade A/B/C/D, units-off, 7d-change, drift chip. Fabric tables
  `cfc_pred_vs_actual`/`cfc_daily_accuracy` (built by notebook), fall back to local backtest parquet
  (`1-WMAPE`, `AVG(ABS(y-p50))`). Verified live: acc 73.8%, ~2.3 units off, +1.1% vs 7d, source=local.
- **Demand un-censoring** (`fabric/_build_notebook.py`, notebook 27 cells): `predict()` adds `is_stockout`
  (conservative: zero-sales-day w/ rmean_28>1, OR 2-day rmax ceiling) + `demand_est`=max(observed,P85) to
  `cfc_order_plan`. Sales≠demand. New tables `cfc_pred_vs_actual`+`cfc_daily_accuracy` emit on predict/backtest/auto.
- **EDA surfaced** (`web/src/routes/eda` + nav): `/eda` "Demand EDA" reads existing `GET /eda` (local DuckDB),
  by-DOW + by-month charts, top products/outlets. Nav now 12 screens (added Demand EDA + Accuracy).
- **UI polish pass**: shared `.btn*` everywhere, cursor-pointer/focus rings, emoji→`<Icon>` SVG swept
  (insights/pipeline/ordering/learning/deploy/results/schema), Overview gradient off-palette blue→terracotta fixed.
- ★★★PENDING: `OPENROUTER_API_KEY` MISSING in `.env.prod` → explain uses offline template (plain, no GLM) until set.
  Fabric notebook edits NOT yet run w/ creds → accuracy falls back to local until job materializes new tables.
  Rotate `FABRIC_PASSWORD`. All Phase-4 work UNCOMMITTED.

## Key files
- `schema_cfc_bakery.md` — THE data model reference.
- `PROJECT_PLAN.md` — 11-phase ML plan. `APP_BUILD_PLAN.md` — operator-app build log. `README.md` — status.
- `src/extract.py` (staged, chunked, resumable, incremental fact sync), `src/eda.py`.
- `reports/extract_qc.md`, `reports/demand_profile.md`.
