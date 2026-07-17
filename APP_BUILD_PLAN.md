# CFC Forecaster — App Build Plan (phase × subtask)

Stack: **SvelteKit 5 + Tailwind + shadcn-svelte** (web) · **FastAPI + DuckDB + pyodbc** (api) ·
**parquet** (forecast) + **Postgres** (uploads/audit). Reuses existing `src/*.py` engine untouched.
Neutral naming — no model/method names in UI. Claude skin (cream/clay, serif, airy).

Legend: ☐ todo · ✎ output · ✓ done-when

---

## P0 · Scaffold & infra
- ☐ Monorepo: `api/`, `web/`, `docker-compose.yml`; keep `src/` + `data/` as-is.
- ☐ FastAPI skeleton + healthcheck; CORS to web.
- ☐ SvelteKit 5 app (runes) + Tailwind + shadcn-svelte init.
- ☐ Postgres container; `.env` wiring (reuse Fabric creds, gitignored).
- ☐ DuckDB attaching `data/predictions/*.parquet` + `data/raw/*.parquet`.
- ✎ `docker compose up` → web + api + pg boot, /health green.
- ✓ both apps run, api reads one parquet via DuckDB.

## P1 · Backend read API (the data spine)
- ☐ `deps/duck.py` — read-only DuckDB conn, parquet views (order_plan, backtest_preds, dim_product, dim_branch).
- ☐ `routes/demand.py`:
  - ☐ `GET /network?date` → L1 outlet rollup (order u, ₭, sku count, accuracy).
  - ☐ `GET /outlet/{id}?date` → L2 every SKU (expected/safe/max/order/trend).
  - ☐ `GET /sku?outlet&product&date` → L3 detail + 30-day history + drivers.
- ☐ Neutral field mapping: p50→expected, p85→safe, p95→max (strip internal names server-side).
- ☐ `routes/order.py`: `GET /picklist?date`, `GET /production?product`, `GET /picklist?warehouse`.
- ✎ JSON endpoints returning REAL numbers from existing parquet.
- ✓ curl L1/L2/L3 returns correct per-outlet×per-SKU rows.

## P2 · Frontend shell + design system
- ☐ Claude tokens in Tailwind config (cream #F5F1EA, clay #C96442, sage, serif display).
- ☐ App shell: left rail nav, top bar, page container.
- ☐ shadcn-svelte primitives themed: Card, Pill/Button, Table, Dialog, Badge, ProgressBar.
- ☐ Sparkline + forecast-band chart component (Chart.js wrapper).
- ✎ `/styleguide` page showing all components in skin.
- ✓ look matches the Claude mockups; reusable component lib.

## P3 · Network drill (L1 → L2 → L3)  ← core value
- ☐ `/` Home: readiness bar + today KPIs + next-steps (P2 mockup).
- ☐ `/network` L1: outlet list, search, sort, date picker, CSV export.
- ☐ `/network/[outlet]` L2: SKU grid (TanStack Table, virtual scroll 200+ rows), expected/safe/max/order/trend, zero-demand collapse.
- ☐ `/network/[outlet]/[sku]` L3: tomorrow numbers + 30-day history chart + plain "why" drivers + override.
- ☐ Wire to P1 endpoints; loading/empty/new-outlet states.
- ✎ clickable L1→L2→L3 on real data.
- ✓ client can drill any shop → any product → see forecast + why.

## P4 · Data Hub (sync + manual + gaps)
- ☐ `routes/data.py`: `GET /sync/status` (15 tables, rows, freshness), `POST /sync/run` (calls extract.py).
- ☐ `GET /data/manual` (weather/holidays/promo files state).
- ☐ `GET /data/gaps` → 12 items + owner + status (from the gaps list).
- ☐ `/data` page: 3 zones (synced · manual · needs-upload) per mockup, freshness badges.
- ✎ Data hub shows live sync state + gap list.
- ✓ sync button refreshes; gaps render with owners.

## P5 · Upload pipeline (template → fill → upload → write)
- ☐ `GET /data/template/{key}` → pre-filled .xlsx/.csv (Fabric keys + names, blank value cols).
- ☐ `POST /data/upload/{key}` → validate (key-match, range, blanks), preview, accept.
- ☐ On accept: write to engine file (`product_econ.csv`, `inventory_daily.parquet`) + log row in PG.
- ☐ `/data/upload/[key]` 3-step UI (download · upload · confirm) per P10 mockup.
- ☐ Validators per gap (economics, inventory, lead-time, promo …).
- ✎ user downloads template, fills, uploads, engine file updated.
- ✓ product_economics upload → `order_qty build` picks it up, readiness ticks.

## P6 · Ordering (picklist · dial · by-product · per-WH)
- ☐ `/ordering` warehouse picklist + service dial (live recompute stockout/waste/cost).
- ☐ `routes/order.py` sweep endpoint for dial points.
- ☐ "By product" tab → per-product network roll (central-kitchen production sheet).  ← gap fix
- ☐ Per-warehouse filter (StockIn/StockOut routing).  ← gap fix
- ☐ Export picklist.csv + "Send to Ops" (email/stub).
- ✎ picklist + dial + production sheet + per-WH split.
- ✓ ops gets per-outlet send list AND per-product make list.

## P7 · Results + Self-learning + Pipeline runner
- ☐ `routes/results.py` parse `eval.md`/`model_lgbm.md` → accuracy/calibration/by-size (neutral).
- ☐ `/results` page (P8 mockup) + "Export brief" → existing deck builders.
- ☐ `routes/pipeline.py`: `POST /run/{stage}` + SSE live log stream.
- ☐ `/pipeline` runner (P2-pipeline mockup) with stage status + live log.
- ☐ `routes/learning.py` from `drift_monitor.md` + champion.json; `/learning` page (P9).
- ✎ results, drift, and one-click stage runs in UI.
- ✓ non-technical user sees "how good" + system self-heals view.

## P8 · Gap-payoff + schema (close the 4 holes)
- ☐ Schema/ER drawer in Data (15 tables, columns, links — from DATA_DICTIONARY).
- ☐ Inventory-uploaded → stockout-correction view (0-sold vs sold-out split).
- ☐ Promo-uploaded → uplift view.
- ☐ Lifecycle dates → explain-zeros annotations on charts.
- ✎ uploaded extra data shows its payoff, not just stored.
- ✓ each gap has a download AND a result screen.

## P9 · Auth · audit · schedule · deploy
- ☐ Read-only auth (Fabric session); role gate (ops/finance/admin).
- ☐ Audit log (uploads, overrides, syncs) in PG → `/settings` view.
- ☐ Scheduler: nightly `predict` + weekly `retrain` (cron/APScheduler) + status.
- ☐ `/settings` (P11): reconnect, schedule, econ status, brand.
- ☐ Harden: input validation, error states, empty/new-outlet, mobile-narrow.
- ☐ Dockerize prod; one-command deploy; backup parquet+PG.
- ✎ production-deployable, audited, scheduled.
- ✓ runs unattended; nightly plan + weekly check + audit trail.

---

## Sequencing (risk-first)
P0 → P1 → P2 → **P3 (demo-able core)** → P4 → P5 → P6 → P7 → P8 → P9.
First demo after **P3** (real per-outlet/per-SKU drill). First production-useful after **P6**.
Full vision at **P9**.

## Done = whole system
sync DB → fill gaps → per-outlet×per-SKU forecast → order → picklist → results → self-learn,
all in Claude skin, engine names hidden, scheduled + audited.
