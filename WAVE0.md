# Wave 0 — Scaffold + conventions (P0 DONE)

Foundation is laid. This file = the contract Wave-1/2 agents build on. The whole point of
Wave 0: make feature slices **touch only their own files** so 4 agents run in parallel with
near-zero merge conflict.

## What exists
```
api/
  main.py            STABLE — never names a feature; includes self-registered routers
  routes/__init__.py auto-registry: any routes/<name>.py with `router` is mounted
  routes/demand.py   REFERENCE slice (L1 network / L2 outlet / L3 sku) — proven on real parquet
  deps/duck.py       DuckDB spine + field-neutralizer (p50/85/95 -> expected/safe/max)
  models/contracts.py  shared response shapes (client-facing names only)
  requirements.txt · Dockerfile
web/
  src/app.css        Claude tokens (cream/clay, serif, pill, card)
  tailwind.config.ts colors: bg surface ink muted accent sage warn line
  src/lib/nav/registry.ts  nav-as-data (append one line, never edit shell)
  src/lib/api.ts     typed client mirroring contracts (/api proxy -> :8000)
  src/routes/+layout.svelte  app shell renders NAV
  src/routes/+page.svelte    Home stub (hits /health live)
  src/routes/styleguide/+page.svelte
docker-compose.yml   db (pg) + api (mounts src/ data/) + web
```

## Proven
- DuckDB spine reads real `data/predictions/order_plan.parquet`: 608,261 rows, 84 dates.
- L1 query returns real outlet names + order units. Pattern works end-to-end.

## Rules for parallel slices (so no collisions)
1. **Backend:** add ONE file `api/routes/<feature>.py` with `router = APIRouter(prefix="/<feature>")`.
   Auto-mounted. Never edit `main.py`.
2. **Frontend:** add your pages under `web/src/routes/<feature>/`. Add ONE line to
   `src/lib/nav/registry.ts`. Never edit `+layout.svelte`.
3. **Field names:** query the neutral DuckDB views (`forecast`, `dim_product`, `dim_branch`,
   `backtest`). Never expose p50/p85/p95/quantile/newsvendor/LightGBM to the client.
4. **New response shapes:** append a class to `models/contracts.py` + a type to `api.ts` (append-only).
5. **Engine:** call existing `src/*.py` via a thin `services/` wrapper; don't fork engine logic.
6. **Uploads/business data:** Postgres only (separate dep, Wave-2 B adds it). Parquet stays read-only.

## Run (in Docker)
```
docker compose up --build         # web :5173 · api :8000 · pg :5433
open http://localhost:5173        # Home + styleguide
open http://localhost:8000/docs   # OpenAPI (contracts visible)
```

## Wave-2 slice assignment (each = own route + own pages)
| Agent | Backend file | Web routes | Nav line |
|---|---|---|---|
| A Network | extend `routes/demand.py` | `network/`, `network/[outlet]`, `network/[outlet]/[sku]` | exists |
| B Data+Upload | `routes/data.py` | `data/`, `data/upload/[key]` | exists |
| C Ordering | `routes/order.py` | `ordering/` (+ by-product, per-WH) | exists |
| D Results+Learning | `routes/results.py`, `routes/learning.py`, `routes/pipeline.py` | `results/`, `learning/` | exists |

Conflict surface after this = nearly nil. Use worktree isolation per agent for safety.
