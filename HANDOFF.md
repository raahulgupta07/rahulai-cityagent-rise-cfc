# CFC Demand Forecasting — Handoff / Runbook

End-to-end system: forecast daily demand per (outlet, product) → newsvendor order qty → warehouse
picklist → self-learning loop with drift monitor. Built Phases 0–9.

## TL;DR — what it does
1. Pulls bakery sales from Microsoft Fabric (user login), aggregates to a (day×branch×product) panel.
2. Builds leak-safe features (lags, rolling, calendar, festivals, weather).
3. Trains LightGBM quantile model (P50/P85/P95). Beats baseline by +16% WMAPE; champion holdout 0.319.
4. Converts forecast → order quantity via newsvendor (critical ratio from margin vs spoilage).
5. Rolls up to a daily warehouse picklist.
6. Nightly predict + weekly retrain (champion/challenger) + drift monitor.

## Open the dashboard
```
open reports/dashboard.html      # macOS — self-contained, KPIs + charts + picklist + drift
```

## Daily / weekly operation
```bash
# nightly — produce tomorrow's order plan from the live champion
python3 src/pipeline.py predict --date YYYY-MM-DD
python3 src/order_qty.py picklist --date YYYY-MM-DD     # warehouse make-list CSV

# weekly — challenge the champion; auto-promotes only if >=1% WMAPE gain
python3 src/pipeline.py retrain

# anytime — drift check; tells you if a retrain is warranted
python3 src/pipeline.py monitor
python3 src/dashboard.py                                # refresh dashboard
```

## When to retrain
- `monitor` verdict = RETRAIN RECOMMENDED **and** accuracy drift = yes (recent WMAPE > champion +10%).
- Data drift alone (e.g. weather PSI high in monsoon) is expected seasonality — not urgent on its own.
- Champion/challenger guard means a worse model never goes live; safe to retrain often.

## ⚠️ Make it production-grade — the ONE real gap
Order quantities use **DEMO economics** (`data/product_econ.csv`: GM 35%, shelf-life 1 day, no salvage).
At uniform critical ratio the newsvendor ≈ flat P50 — no extra value. **The unlock is real per-product
economics.** Get from CFC finance/ops and edit `data/product_econ.csv`:
| column | meaning | source |
|---|---|---|
| `gm` | gross margin fraction | finance (per product or category) |
| `shelf_life_days` | days before spoilage (1=same-day) | ops (bread 1 / frozen 90 / ambient ∞) |
| `salvage_frac` | cost fraction recovered on unsold (markdown/staff) | ops |
Then re-run `order_qty build` + `pipeline predict`. High-margin/long-shelf SKUs will earn safety stock;
perishables stay lean. No code change needed.

## Data pipeline (rebuild from scratch)
```bash
python3 src/extract.py small && python3 src/extract.py fact   # Fabric → data/raw/ (per-table approval)
python3 src/features.py                                        # → data/features/train.parquet
python3 src/baselines.py ; python3 src/train.py               # floor + model
python3 src/backtest.py                                        # walk-forward eval + sim
python3 src/order_qty.py build                                 # order policy
python3 src/pipeline.py retrain                                # register champion
python3 src/dashboard.py                                       # dashboard
```

## Key files
| Path | What |
|---|---|
| `fabric_user_connector.py` | Fabric DB access (user login). Creds in `.env` (gitignored). |
| `schema_cfc_bakery.md` | data model reference |
| `src/features.py` | feature engineering (leak-safe) |
| `src/train.py` / `src/backtest.py` | model + walk-forward eval |
| `src/order_qty.py` | newsvendor order qty + picklist + service sweep |
| `src/pipeline.py` | self-learning: retrain / predict / monitor |
| `src/dashboard.py` | builds `reports/dashboard.html` |
| `data/product_econ.csv` | **edit with real margin + shelf-life** |
| `models/champion.json` | live model pointer; `models/registry/` versions |
| `reports/` | baselines, model_lgbm, eval, order_policy, service_tradeoff, drift_monitor, dashboard.html |

## Results snapshot
- LightGBM P50 WMAPE 0.341 vs baseline floor 0.405 = **+16%**, stable across folds + ABC classes.
- Quantiles calibrated: P85 cover 85.4%, P95 94.5% → safe for safety-stock.
- Champion `v_20260424` holdout WMAPE **0.319** (beats stretch target ≤0.321).
- Business sim: at GM 35%, cost-min near P50; picklist ~30k units/day across ~230 products.

## Security / ops notes
- Read-only on Fabric; aggregate server-side; never pull raw billion-row POS.
- Credentials in `.env` only. **Rotate the password** (it was pasted in chat during build).
- Per-table extraction approval is the working rule — see `CLAUDE.md`.

## Backlog (optional, not blocking)
- Croston/SBA for the intermittent tail (~16% of volume) — LightGBM weak on lumpy series.
- Optuna tuning to push P50 below 0.319.
- Branch→warehouse routing in picklist (keys exist: `dim_branch.StockInId/StockOutId`, `dim_warehouse`).
- Extend weather back to Jan 2023; fill branch ChannelId nulls.

---

# Operator app — production deploy (Docker single-host)

The agentic AutoML operator app (`web/` + `api/`) ships as a self-contained Docker stack.
Full build detail in `APP_BUILD_PLAN.md`; app conventions in `CLAUDE.md`.

## Stack
```
caddy (:80/:443, auto-TLS)  ──/api/*──►  api  (FastAPI, 1 uvicorn worker)
                            ──/*───────►  web  (SvelteKit adapter-node :3000)
```
Operational store = **SQLite** (`deps/db.py`, volume `appstore`). No Postgres.
Forecasting data = parquet + DuckDB (mounted `./data`, `./models`, `./reports`).

## First deploy
```bash
cp .env.example .env.prod
# fill: SECRET_KEY (openssl/py secrets), ALLOWED_ORIGINS, ORIGIN, DOMAIN, FABRIC_* (if sync)
python3 -c "import secrets;print(secrets.token_hex(32))"   # → SECRET_KEY
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml logs -f api      # watch startup
curl -sk https://<DOMAIN>/api/health                        # {"ok":true,...}
```

## Security (fail-closed)
- Prod boot **ABORTS** if `SECRET_KEY` is unset/default or `AUTH_DISABLED=1`. This is enforced, not advisory.
- CORS denies all cross-origin unless `ALLOWED_ORIGINS` lists your origin.
- `.env` / `.env.prod` are gitignored — never commit secrets. Rotate `FABRIC_PASSWORD` regularly.

## Operating rules
- **One api worker only.** The heavy-run lock + job registry are in-process; more workers would
  run concurrent trainings. Scale via schedule, not workers. (Multi-node → needs a Redis lock first.)
- Heavy stages (train/backtest/retrain/sync) run one at a time; a 2nd request returns `[ERROR] busy`.
- Live Fabric sync needs `FABRIC_*` creds; without them the app runs on existing parquet.
- LLM narration (Autopilot) needs `OPENROUTER_API_KEY` (OpenRouter only); optional — templates fall back.

## Tests
```bash
cd api && python3 -m pytest tests/ -q     # 27: routes 200, zero-leak, stores, validate, security
```
`test_neutralize.py` guards the hard rule: no model/method/metric name (WMAPE, P50/85/95,
LightGBM, newsvendor, quantile…) may reach the operator UI.

## Known gap (data correctness)
- Per-warehouse picklist falls back to network-wide: `dim_branch.StockOutId` ≠ `dim_warehouse.WarehouseId`
  (wrong join key). Needs a StockLocation route mapping before per-WH numbers are trusted.
