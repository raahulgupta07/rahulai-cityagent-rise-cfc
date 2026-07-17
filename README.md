# City Agent RISE

**RISE** = **R**eplenishment **I**ntelligence & **S**tock **E**ngine.

AI demand forecasting + smart ordering for the **CityFood Concepts (CFC)** bakery network.
Forecasts daily demand per (outlet × product), turns it into warehouse order quantities that
cut both stockouts and waste, and serves the whole thing as a one-page operator dashboard.

> This repo is **code only** — trained models, raw data, generated decks, and secrets are
> excluded (`.gitignore`). Models regenerate from `src/train.py` or the Fabric notebook; live
> data comes from Microsoft Fabric or files you provide. See **First run** below.

---

## What it does

- **Forecast** — LightGBM quantile model (P50/P85/P95) per outlet × product, leak-safe features
  (lags, rolling stats, calendar, festivals, weather).
- **Order** — newsvendor policy converts the forecast distribution into daily order quantities +
  a warehouse picklist.
- **Self-learn** — champion/challenger with drift monitoring; promote only on real accuracy gain.
- **Operate** — one-page **Overview** (live snapshot cache), model leaderboard/evidence, smart
  ordering, accuracy, monitoring, and a live "Run Experiment" pipeline.
- **Access** — email/password login (env-based) + optional **Keycloak / OIDC SSO**.

---

## Stack

| Layer | Tech |
|---|---|
| Web | SvelteKit 5 (runes) + Tailwind (`web/`) |
| API | FastAPI + DuckDB + pyodbc, 1 worker (`api/`) |
| Engine | LightGBM + pandas + statsforecast (`src/*.py`) |
| Heavy ML | Microsoft Fabric notebook (`fabric/`) |
| Store | SQLite (`data/app.db`) + parquet (read via DuckDB) |
| Proxy | Caddy (auto-TLS) |

---

## Repo layout

```
api/            FastAPI app (routes/ self-register; deps/ = duck, fabric, auth, oidc, jobs)
web/            SvelteKit app (routes/, lib/api clients, lib/nav)
src/            ML engine — extract, features, train, backtest, order_qty, pipeline
fabric/         Fabric notebook + build/push scripts (heavy training)
deploy/         Caddyfile + AWS deploy guide (deploy/README.md)
docker-compose.prod.yml   production stack (caddy + api + web)
.env.example    config template  →  copy to .env.prod
```

---

## Installation

### Prerequisites
- **Docker** + Docker Compose v2 (production / simplest), **or**
- **Python 3.11** + **Node 18+** (local dev)

### Option A — Docker (production / single host)

```bash
git clone git@github.com:raahulgupta07/rahulai-cityagent-rise-cfc.git
cd rahulai-cityagent-rise-cfc

cp .env.example .env.prod
python3 -c "import secrets;print(secrets.token_hex(32))"   # → put in SECRET_KEY
# edit .env.prod: SECRET_KEY, SUPERADMIN_EMAIL/PASSWORD, DOMAIN/ORIGIN, FABRIC_* (optional)

docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```
Open the site, sign in with the superadmin email/password. Full AWS runbook: **[`deploy/README.md`](deploy/README.md)**.

Local HTTP test (no domain): set `DOMAIN=:80`, `HTTP_PORT=8080` → `http://localhost:8080`.

> The API image is **baked** — after code changes, rebuild (`up -d --build api web`); a plain
> restart serves stale code.

### Option B — Local dev (hot reload)

```bash
# API (terminal 1)
cd api && pip install -r requirements.txt -r requirements-engine.txt
AUTH_DISABLED=1 APP_ENV=dev python -m uvicorn main:app --port 8811

# Web (terminal 2)
cd web && npm install
API_PROXY=http://127.0.0.1:8811 npm run dev -- --port 8812      # open http://localhost:8812
```

---

## First run — where does data come from?

The repo ships **no models or data**. Pick one:

- **Live from Fabric (recommended)** — set `USE_FABRIC=1` + `FABRIC_*` creds in `.env.prod`. On
  boot the app reads results from the Lakehouse `cfc_*` tables and caches them. Nothing to ship.
- **Regenerate locally** — with a data source configured, rebuild the pipeline:
  ```bash
  python src/extract.py small && python src/extract.py fact   # Fabric → data/raw/
  python src/features.py                                       # feature matrix
  python src/train.py                                          # LightGBM P50/85/95 → models/
  python src/backtest.py && python src/order_qty.py build      # eval + order policy
  python src/pipeline.py retrain                               # register champion
  ```

With no data source and no local files, the dashboard is empty until you connect Fabric or upload.

---

## Configuration (`.env.prod`)

| Key | Purpose |
|---|---|
| `SECRET_KEY` | token signing — **required**, boot fails on default in prod |
| `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` | admin login |
| `AUTH_USERS` | extra users `email:password:role,...` (viewer\|ops\|finance\|admin) |
| `DOMAIN` / `ORIGIN` / `ALLOWED_ORIGINS` | public address + CORS (auto-TLS on a real domain) |
| `USE_FABRIC` + `FABRIC_*` | live Microsoft Fabric reads / notebook jobs |
| `OIDC_*` | Keycloak / OIDC SSO (off by default) |
| `CFC_TRAIN_LEAN` / `CFC_MAX_ROWS` | in-container training memory guard |
| `OPENROUTER_API_KEY` | optional LLM narration (OpenRouter only) |

Secrets live in `.env.prod` only (gitignored). Never commit it.

---

## Overview data — Refresh vs Sync

The Overview loads instantly from a local snapshot (`data/cache/overview.json`), rebuilt in the
background on boot:
- **↻ Refresh** — re-read the saved snapshot (instant).
- **Sync live** — pull fresh from Fabric + local and re-cache (~30s, with progress).

Training is separate: **Run Experiment** streams a live step-by-step log.

---

## SSO (Keycloak / OIDC)

Off by default. Set `OIDC_ENABLED=1` + `OIDC_*` in `.env.prod`, register a confidential client in
Keycloak with redirect URI `<ORIGIN>/api/auth/sso/callback`, rebuild the API. The login page then
shows **Continue with Keycloak**; **Settings → Single Sign-On** reports status. Email login still works.

---

## Tests

```bash
cd api && python3 -m pytest tests/ -q
```

---

## Deploy

**AWS single-host runbook:** [`deploy/README.md`](deploy/README.md).
Architecture, sizing, DNS/TLS, `.env.prod`, day-2 ops, backups.
