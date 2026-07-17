# CityAI CFC — Master Plan (data → forecast → app)

End-to-end plan for CFC bakery demand forecasting + the operator app on top.
Forecast engine = **DONE** (9 phases). App = **planned** (P0–P9 below).
Detail files: `schema_cfc_bakery.md` · `DATA_DICTIONARY.md` · `APP_BUILD_PLAN.md` · `HANDOFF.md`.

---

## 0 · Goal
- 84 outlets order fresh bakery from a central warehouse daily.
- Forecast demand per **(outlet, product, day)** → smart order quantities → warehouse picklist.
- Cut stockouts AND waste. Self-learning. Operator app in front, engine names hidden.

## 1 · Data (status)
- **Have** (Fabric `HUB_REPORTING_DB`): 15 tables — sales fact (13.4M) + 11 masters/dims. 7.08M-row
  panel extracted. Plus weather + Myanmar holidays (manual). See `DATA_DICTIONARY.md`.
- **Missing** (12 inputs → app upload flow): product economics (margin/cost/shelf-life/salvage),
  daily inventory + **wastage**, lead-time/SLA, order history, promo calendar, lifecycle dates.
- Target = `net_units = Quantity − Refund − Void`. Refund/Void ≠ waste (POS reversals).

---

## PART A — Forecast engine  ✅ DONE (9 phases, in `src/`)

| Phase | Output |
|---|---|
| 0 Setup & scope | scope, Fabric connector |
| 1 Extract | `data/raw/` panel + 11 masters (`extract.py`) |
| 2 EDA | `reports/demand_profile.md` (`eda.py`) |
| 3 Features | `train.parquet` 8.33M×35, leak-safe (`features.py`) |
| 4 Baselines | floor WMAPE 0.401 (`baselines.py`) |
| 5 Model | quantile P50/P85/P95, WMAPE 0.341 +16% (`train.py`) |
| 6 Backtest | walk-forward 3 folds + cost sim (`backtest.py`) |
| 7 Order qty | per-product newsvendor + picklist (`order_qty.py`) |
| 8 Self-learning | champion/challenger + drift, champ 0.319 (`pipeline.py`) |
| 9 Dashboard | `reports/dashboard.html` + `HANDOFF.md` |

**Approach (locked):** target = units per (outlet,product,day); lag/rolling/calendar/holiday/weather/
promo features; quantile forecast (Expected/Safe/Max); newsvendor order = demand quantile at critical
ratio (margin vs spoilage); WMAPE + pinball, walk-forward backtest (no random split); champion/
challenger self-learning. Pitfalls handled: cold-start fallback, leak-safe shift≥1, festival calendar,
intermittent tail (Croston = backlog).

**One real gap:** order-sizing runs on placeholder economics → uniform critical ratio → orders ≈
middle estimate. Real per-product margin + shelf-life (the upload flow) unlocks differentiated ordering.

---

## PART B — Operator app  ☐ PLANNED

**Stack:** SvelteKit 5 + Tailwind + shadcn-svelte (web) · FastAPI + DuckDB + pyodbc (api) ·
parquet (forecast) + Postgres (uploads/audit). Reuses `src/*.py` untouched. Claude skin, neutral naming.

**15 pages:** Connect · Home · Data Hub · Network(L1) · Outlet(L2) · SKU(L3) · Ordering ·
Results · Learning · Upload-flow · Settings · + 4 gap pages (production sheet · per-WH picklist ·
schema/ER view · gap-payoff screens).

**Phases (detail + subtasks in `APP_BUILD_PLAN.md`):**

| Phase | Goal | Demo gate |
|---|---|---|
| P0 | Scaffold: monorepo, FastAPI+SvelteKit+PG+DuckDB boot | apps run |
| P1 | Backend read API — DuckDB drill L1/L2/L3 + picklist (neutral fields) | curl real rows |
| P2 | Frontend shell + Claude design system | styleguide |
| **P3** | **Network drill L1→L2→L3 on real data** | **★ first demo** |
| P4 | Data Hub — sync · manual · 12 gaps | gaps render |
| P5 | Upload pipeline — template→validate→write engine file | econ upload works |
| **P6** | **Ordering — picklist · dial · by-product · per-WH** | **★ production-useful** |
| P7 | Results + Learning + pipeline runner (SSE) | "how good" view |
| P8 | Gap-payoff + schema view (closes 4 coverage holes) | each gap has payoff |
| P9 | Auth · audit · schedule · deploy | unattended + audited |

**Sequencing:** risk-first P0→P9. First demo after **P3**, useful after **P6**, full at **P9**.

---

## 2 · Definition of done (whole system)
Sync DB → fill gaps via upload → per-outlet × per-SKU forecast (Expected/Safe/Max) → order qty →
warehouse picklist + per-product production sheet → results + self-learning, all in Claude skin,
engine names hidden, nightly predict + weekly retrain, audited. Only true unlock left = real
per-product economics + inventory/wastage data from the business.
