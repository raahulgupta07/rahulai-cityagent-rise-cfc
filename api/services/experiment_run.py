"""
Full-experiment orchestration — chains the whole ML pipeline as ONE run and streams
rich, structured events so the UI can render a live CLI log + stage stepper + metric
cards + a "training in progress" animation.

Two modes:
  • sim  (default) — a scripted rehearsal. No Fabric pull, no training. Emits realistic
                     step-by-step events (monthly fact batches, per-quantile training
                     iterations, per-fold WMAPE) with small sleeps so the UI feels alive.
                     Demo-safe, instant-ish (~20s), needs no creds.
  • real — actually runs each stage via services.runner.stream_stage (guard_run=False):
                     Fabric monthly-batch extract, feature build, LightGBM train,
                     walk-forward backtest, gate, order, predict, monitor. ~12–14 min,
                     one at a time (experiment lock).

Every event is a JSON object yielded as a raw string (EventSourceResponse wraps it as
`data:` — NEVER pre-prefix). Event schema:

  {type:"experiment_start", version, cutoff, mode, stages:[{id,label}...], total}
  {type:"stage_start", stage, label, idx, total, note}
  {type:"log",   stage, level:"info|good|warn|err", source, msg, rows?, secs?, ts}
  {type:"metric",stage, key, label, value, unit?}          # feeds live metric cards
  {type:"progress", stage, pct, note}                       # feeds the training animation
  {type:"stage_done", stage, status:"ok|error", secs, summary}
  {type:"gate",  promoted, challenger, champion, gain}
  {type:"done",  version, wmape, promoted, secs}
  {type:"error", stage, msg}
"""
from __future__ import annotations
import asyncio
import json
import pathlib
import re
from datetime import datetime, timedelta
from typing import AsyncIterator

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

# Default chain — the whole thing. `sync` = incremental Fabric pull (monthly batches).
FULL_CHAIN = [
    ("extract",  "Data extraction · dims"),
    ("sync",     "Sales download · monthly batches"),
    ("features", "Feature engineering"),
    ("train",    "Model training · LightGBM quantile"),
    ("backtest", "Backtest · walk-forward"),
    ("gate",     "Champion / challenger gate"),
    ("order",    "Order quantities · newsvendor"),
    ("predict",  "Daily predictions"),
    ("monitor",  "Drift & health check"),
]
_LABELS = dict(FULL_CHAIN)


def _ev(**kw) -> str:
    return json.dumps(kw, default=str)


def _hms() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _new_version() -> str:
    return "v_" + datetime.now().strftime("%Y%m%d_%H%M")


def resolve_stages(stages: str | None) -> list[tuple[str, str]]:
    """Comma list of ids → ordered (id,label) chain. None/empty → full chain."""
    if not stages:
        return FULL_CHAIN
    want = [s.strip() for s in stages.split(",") if s.strip()]
    return [(sid, _LABELS.get(sid, sid)) for sid in want if sid in _LABELS or sid == "gate"]


# ── metric parsing (real mode) ───────────────────────────────────────────────
_RE_BATCH = re.compile(r"batch\s+(\d{6}):\s+([\d,]+)\s+rows", re.I)
_RE_WMAPE = re.compile(r"wmape[^0-9]*([0-9]*\.[0-9]+)", re.I)
_RE_FOLD  = re.compile(r"fold\s*(\d+)[^0-9]*([0-9]*\.[0-9]+)", re.I)
_RE_ITER  = re.compile(r"\[(\d+)\].*?(?:l1|l2|loss)[:\s]+([0-9]*\.[0-9]+)", re.I)
_RE_ROWS  = re.compile(r"([\d,]{4,})\s*(?:rows|series|u\b|units)", re.I)


def _classify(line: str) -> str:
    l = line.lower()
    if "[error]" in l or "traceback" in l or "error" in l:
        return "err"
    if "[done]" in l or "✓" in line or "promote" in l or "saved" in l:
        return "good"
    if "warn" in l or "drift" in l:
        return "warn"
    return "info"


# ── simulation script (demo-safe animation) ─────────────────────────────────
_DIMS = [
    ("dim_branch", 77), ("dim_product", 1204), ("dim_warehouse", 143),
    ("dim_stocklocation", 892), ("dim_uom", 34), ("dim_partner", 210),
    ("dim_channel", 8), ("dim_company", 12), ("dim_costcenter", 96),
    ("dim_profitcenter", 61), ("dim_segment", 9),
]


def _sim_months() -> list[str]:
    out, y, m = [], 2023, 1
    while (y, m) <= (2026, 6):
        out.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


async def _sleep(speed: float, base: float):
    await asyncio.sleep(base / max(0.25, speed))


async def _simulate(chain, cutoff, version, speed) -> AsyncIterator[str]:
    import random  # deterministic-ish jitter for realism (not security-sensitive)
    rng = random.Random(42)
    t0 = datetime.now()

    for idx, (sid, label) in enumerate(chain):
        yield _ev(type="stage_start", stage=sid, label=label, idx=idx, total=len(chain))
        s0 = datetime.now()

        if sid == "extract":
            yield _ev(type="log", stage=sid, level="info", source="fabric",
                      msg="connect HUB_REPORTING_DB (ActiveDirectoryPassword, tls)", ts=_hms())
            await _sleep(speed, 0.5)
            yield _ev(type="log", stage=sid, level="good", source="fabric", msg="handshake ok", secs=0.6, ts=_hms())
            for name, n in _DIMS:
                await _sleep(speed, 0.12)
                yield _ev(type="log", stage=sid, level="info", source="fabric",
                          msg=f"pull {name}", rows=n, secs=round(rng.uniform(0.3, 0.7), 1), ts=_hms())
            yield _ev(type="stage_done", stage=sid, status="ok", secs=round((datetime.now()-s0).total_seconds(), 1),
                      summary=f"{len(_DIMS)} dim tables")

        elif sid == "sync":
            months = _sim_months()
            total_rows = 0
            yield _ev(type="log", stage=sid, level="info", source="fabric",
                      msg=f"edm.CFC_PBID_Sales_Summary — INCREMENTAL, {len(months)} monthly batches", ts=_hms())
            for i, mk in enumerate(months):
                await _sleep(speed, 0.08)
                r = rng.randint(240_000, 330_000)
                total_rows += r
                yield _ev(type="log", stage=sid, level="info", source="fabric",
                          msg=f"batch {mk} · SUM(net_units) GROUP BY DayKey,BranchId,ProductId",
                          rows=r, secs=round(rng.uniform(2.4, 3.4), 1), ts=_hms())
                yield _ev(type="progress", stage=sid, pct=round((i + 1) / len(months) * 100), note=f"{mk}")
            await _sleep(speed, 0.2)
            yield _ev(type="log", stage=sid, level="good", source="fabric",
                      msg="upsert on DayKey×BranchId×ProductId (7-day overlap re-pull)", ts=_hms())
            yield _ev(type="metric", stage=sid, key="rows", label="Sales rows", value=total_rows)
            yield _ev(type="stage_done", stage=sid, status="ok",
                      secs=round((datetime.now()-s0).total_seconds(), 1), summary=f"{total_rows/1e6:.2f}M rows")

        elif sid == "features":
            for src, msg, rows in [
                ("web", "holidays MM 2023-26", 312), ("web", "weather daily (branch→city)", 0),
                ("web", "fx MMK/USD", 730)]:
                await _sleep(speed, 0.15)
                yield _ev(type="log", stage=sid, level="info", source=src, msg=msg,
                          rows=rows or None, secs=0.3, ts=_hms())
            await _sleep(speed, 0.3)
            yield _ev(type="log", stage=sid, level="info", source="panel",
                      msg="join sales × dims × calendar, zero-fill active series", rows=7_080_000, secs=6.1, ts=_hms())
            await _sleep(speed, 0.3)
            yield _ev(type="log", stage=sid, level="info", source="feat",
                      msg="lags[1,7,14,28] · rmean/rstd[7,14,28] · dow_mean · calendar · promo", ts=_hms())
            await _sleep(speed, 0.2)
            yield _ev(type="log", stage=sid, level="good", source="abc",
                      msg="ABC: A 214 / B 500 / C 490 SKUs", ts=_hms())
            yield _ev(type="metric", stage=sid, key="features", label="Features", value=38)
            yield _ev(type="metric", stage=sid, key="train_rows", label="Train rows", value=6_900_000)
            yield _ev(type="stage_done", stage=sid, status="ok",
                      secs=round((datetime.now()-s0).total_seconds(), 1), summary="38 features · 6.9M rows")

        elif sid == "train":
            for q, alpha in [("P50", 0.50), ("P85", 0.85), ("P95", 0.95)]:
                yield _ev(type="log", stage=sid, level="info", source="lgbm",
                          msg=f"train {q} · objective=quantile alpha={alpha} · 18 categorical", ts=_hms())
                l1 = 0.26
                for it in range(100, 1000, 100):
                    await _sleep(speed, 0.06)
                    l1 = max(0.185, l1 - rng.uniform(0.004, 0.012))
                    yield _ev(type="log", stage=sid, level="info", source="lgbm",
                              msg=f"{q} iter {it}  l1 {l1:.3f}", ts=_hms())
                    yield _ev(type="progress", stage=sid, pct=round(((["P50","P85","P95"].index(q)*900 + it) / 2700) * 100),
                              note=f"{q} · iter {it}")
                yield _ev(type="log", stage=sid, level="good", source="lgbm",
                          msg=f"{q} early-stop · booster saved", ts=_hms())
            yield _ev(type="metric", stage=sid, key="boosters", label="Boosters", value=3)
            yield _ev(type="stage_done", stage=sid, status="ok",
                      secs=round((datetime.now()-s0).total_seconds(), 1), summary=f"3 boosters → registry/{version}")

        elif sid == "backtest":
            fold_w = [0.384, 0.325, 0.306]
            for i, w in enumerate(fold_w, 1):
                yield _ev(type="log", stage=sid, level="info", source="cv",
                          msg=f"fold {i} · retrain <cutoff, score holdout month", ts=_hms())
                await _sleep(speed, 0.5)
                yield _ev(type="log", stage=sid, level="good", source="cv",
                          msg=f"fold {i} WMAPE {w:.3f}", ts=_hms())
                yield _ev(type="metric", stage=sid, key=f"fold{i}", label=f"Fold {i} WMAPE", value=w)
            overall = 0.319
            yield _ev(type="log", stage=sid, level="good", source="cv",
                      msg=f"overall WMAPE {overall:.3f} · P85 cover 85.4% · P95 94.5%", ts=_hms())
            yield _ev(type="metric", stage=sid, key="wmape", label="WMAPE (backtest)", value=overall)
            yield _ev(type="metric", stage=sid, key="cover_p85", label="P85 coverage", value=85.4, unit="%")
            yield _ev(type="stage_done", stage=sid, status="ok",
                      secs=round((datetime.now()-s0).total_seconds(), 1), summary="608k test rows · 3 folds")

        elif sid == "gate":
            champ, chall = 0.341, 0.319
            gain = round((champ - chall) / champ * 100, 1)
            await _sleep(speed, 0.4)
            yield _ev(type="log", stage=sid, level="info", source="gate",
                      msg=f"challenger {chall:.3f} vs champion {champ:.3f}", ts=_hms())
            yield _ev(type="log", stage=sid, level="good", source="gate",
                      msg=f"gain +{gain}% ≥ MIN_GAIN 1% → PROMOTE", ts=_hms())
            yield _ev(type="gate", promoted=True, challenger=chall, champion=champ, gain=gain)
            yield _ev(type="stage_done", stage=sid, status="ok",
                      secs=round((datetime.now()-s0).total_seconds(), 1), summary="PROMOTED")

        elif sid == "order":
            await _sleep(speed, 0.4)
            yield _ev(type="log", stage=sid, level="info", source="newsvendor",
                      msg="critical ratio CR=Cu/(Cu+Co) per (branch,product) · interp P50/85/95", ts=_hms())
            yield _ev(type="metric", stage=sid, key="order_rows", label="Outlet × SKU", value=6355)
            yield _ev(type="stage_done", stage=sid, status="ok",
                      secs=round((datetime.now()-s0).total_seconds(), 1), summary="6,355 outlet×SKU rows")

        elif sid == "predict":
            await _sleep(speed, 0.4)
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            yield _ev(type="log", stage=sid, level="info", source="predict",
                      msg=f"champion booster → order plan {tomorrow}", rows=108_000, ts=_hms())
            yield _ev(type="stage_done", stage=sid, status="ok",
                      secs=round((datetime.now()-s0).total_seconds(), 1), summary="next 14d written")

        elif sid == "monitor":
            await _sleep(speed, 0.4)
            yield _ev(type="log", stage=sid, level="good", source="psi",
                      msg="PSI per feature max 0.04 (<0.10 stable) · accuracy gate held", ts=_hms())
            yield _ev(type="metric", stage=sid, key="psi", label="Max PSI", value=0.04)
            yield _ev(type="stage_done", stage=sid, status="ok",
                      secs=round((datetime.now()-s0).total_seconds(), 1), summary="stable")

        else:
            await _sleep(speed, 0.3)
            yield _ev(type="stage_done", stage=sid, status="ok",
                      secs=round((datetime.now()-s0).total_seconds(), 1), summary="ok")

    yield _ev(type="done", version=version, wmape=0.319, promoted=True,
              secs=round((datetime.now()-t0).total_seconds(), 1))


# ── real run (chains services.runner.stream_stage) ──────────────────────────
async def _run_real(chain, cutoff, version, params) -> AsyncIterator[str]:
    from services.runner import stream_stage, _STAGE_BY_ID
    t0 = datetime.now()
    overall_wmape = None
    promoted = None

    for idx, (sid, label) in enumerate(chain):
        yield _ev(type="stage_start", stage=sid, label=label, idx=idx, total=len(chain))
        s0 = datetime.now()

        # `gate` is not a runner stage — it is folded into `train`/`retrain`'s promote logic.
        # Run it through `retrain` if present; otherwise skip with a note.
        run_id = sid
        if sid == "gate":
            yield _ev(type="log", stage=sid, level="info", source="gate",
                      msg="promotion is decided inside the retrain stage (champion/challenger)", ts=_hms())
            yield _ev(type="stage_done", stage=sid, status="ok",
                      secs=round((datetime.now()-s0).total_seconds(), 1), summary="see train stage")
            continue
        if sid not in _STAGE_BY_ID:
            yield _ev(type="log", stage=sid, level="warn", source="runner", msg=f"no runner for {sid}, skipped", ts=_hms())
            yield _ev(type="stage_done", stage=sid, status="ok", secs=0.0, summary="skipped")
            continue

        status = "ok"
        try:
            async for line in stream_stage(run_id, guard_run=False, params=params):
                lvl = _classify(line)
                if "[ERROR]" in line:
                    status = "error"
                yield _ev(type="log", stage=sid, level=lvl, source="run", msg=line, ts=_hms())

                # opportunistic metric parsing → live cards
                m = _RE_BATCH.search(line)
                if m:
                    yield _ev(type="log", stage=sid, level="info", source="fabric",
                              msg=f"batch {m.group(1)}", rows=int(m.group(2).replace(",", "")), ts=_hms())
                mf = _RE_FOLD.search(line)
                if mf:
                    yield _ev(type="metric", stage=sid, key=f"fold{mf.group(1)}",
                              label=f"Fold {mf.group(1)} WMAPE", value=float(mf.group(2)))
                elif (mw := _RE_WMAPE.search(line)):
                    overall_wmape = float(mw.group(1))
                    yield _ev(type="metric", stage=sid, key="wmape", label="WMAPE", value=overall_wmape)
                if "promote" in line.lower():
                    promoted = True
        except Exception as exc:
            status = "error"
            yield _ev(type="error", stage=sid, msg=str(exc))

        yield _ev(type="stage_done", stage=sid, status=status,
                  secs=round((datetime.now()-s0).total_seconds(), 1), summary="")
        if status == "error":
            yield _ev(type="error", stage=sid, msg="stage failed — experiment halted")
            return

    yield _ev(type="done", version=version, wmape=overall_wmape, promoted=promoted,
              secs=round((datetime.now()-t0).total_seconds(), 1))


# ── Fabric run (real ML in Microsoft Fabric) ─────────────────────────────────
# One notebook job (MODE=all) does features→train→backtest→predict→monitor next to
# the Lakehouse data. We map that single job to a 3-step UI view and stream its status
# into the same CLI-log/stepper schema. Ends with a CHALLENGER awaiting human approval.
FABRIC_CHAIN = [
    ("submit",   "Submit to Fabric"),
    ("run",      "Fabric notebook · full pipeline"),
    ("register", "Register challenger"),
]


async def _run_fabric(cutoff: str | None) -> AsyncIterator[str]:
    from deps import fabric_jobs, fabric

    # 1 · submit
    sid = "submit"; s0 = datetime.now()
    yield _ev(type="stage_start", stage=sid, label="Submit to Fabric", idx=1, total=3,
              note="triggering the CFC_ML_Pipeline notebook (MODE=all)")
    try:
        job = await asyncio.to_thread(fabric_jobs.run, "all", {"CUTOFF": cutoff} if cutoff else {})
    except Exception as exc:
        yield _ev(type="error", stage=sid, msg=f"could not start Fabric job: {exc}")
        return
    jid = job["job_id"]
    yield _ev(type="log", stage=sid, level="good", source="fabric",
              msg=f"job {jid} accepted · running next to Lakehouse data", ts=_hms())
    yield _ev(type="stage_done", stage=sid, status="ok",
              secs=round((datetime.now()-s0).total_seconds(), 1), summary=f"job {jid[:8]}")

    # 2 · run — poll status, heartbeat into the log
    sid = "run"; s1 = datetime.now()
    yield _ev(type="stage_start", stage=sid, label="Fabric notebook · full pipeline", idx=2, total=3,
              note="features → train → backtest → predict → monitor (~15 min)")
    final = None
    for _ in range(160):                       # ~40 min ceiling at 15s
        await asyncio.sleep(15)
        try:
            st = await asyncio.to_thread(fabric_jobs.status, jid)
        except Exception:
            continue
        secs = round((datetime.now()-s1).total_seconds())
        state = st.get("status")
        yield _ev(type="log", stage=sid, level="info", source="fabric",
                  msg=f"notebook {state} · {secs}s elapsed", secs=secs, ts=_hms())
        yield _ev(type="progress", stage=sid, pct=min(95, secs / 9), note=state)
        if state in ("Completed", "Failed", "Cancelled"):
            final = state
            break
    if final != "Completed":
        yield _ev(type="log", stage=sid, level="err", source="fabric",
                  msg=f"job ended: {final or 'still running'}", ts=_hms())
        # surface the Fabric cell traceback if the job wrote one
        try:
            tb = await asyncio.to_thread(fabric.last_error) if hasattr(fabric, "last_error") else None
            if tb:
                yield _ev(type="log", stage=sid, level="err", source="fabric", msg=tb[:800], ts=_hms())
        except Exception:
            pass
        yield _ev(type="stage_done", stage=sid, status="error",
                  secs=round((datetime.now()-s1).total_seconds(), 1), summary=final or "timeout")
        yield _ev(type="error", stage=sid, msg="Fabric run did not complete")
        return
    yield _ev(type="stage_done", stage=sid, status="ok",
              secs=round((datetime.now()-s1).total_seconds(), 1), summary="notebook complete")

    # 3 · register — read the fresh challenger from cfc_model_runs
    sid = "register"; s2 = datetime.now()
    yield _ev(type="stage_start", stage=sid, label="Register challenger", idx=3, total=3,
              note="reading the new run from the Fabric registry")
    version = None; wmape = None
    try:
        rows = await asyncio.to_thread(
            fabric.q, f"SELECT TOP 1 version, wmape, promoted FROM {fabric.table('cfc_model_runs')} ORDER BY created DESC")
        if rows:
            version = rows[0]["version"]; wmape = float(rows[0]["wmape"])
            promoted = bool(rows[0]["promoted"])
            yield _ev(type="metric", stage=sid, key="wmape", label="WMAPE", value=round(wmape, 4))
            yield _ev(type="log", stage=sid, level="good", source="fabric",
                      msg=f"registered {version} as {'champion' if promoted else 'CHALLENGER'} "
                          f"(WMAPE {wmape:.4f}) — awaiting approval", ts=_hms())
            yield _ev(type="gate", promoted=promoted, challenger=version, champion=None, gain=None)
    except Exception as exc:
        yield _ev(type="log", stage=sid, level="warn", source="fabric",
                  msg=f"run done but registry read failed: {exc}", ts=_hms())
    yield _ev(type="stage_done", stage=sid, status="ok",
              secs=round((datetime.now()-s2).total_seconds(), 1), summary=version or "")
    yield _ev(type="done", version=version, wmape=wmape, promoted=False,
              secs=round((datetime.now()-s0).total_seconds(), 1))


# ── public entry ─────────────────────────────────────────────────────────────
async def run_experiment(
    cutoff: str | None = None,
    stages: str | None = None,
    sim: bool = True,
    speed: float = 1.0,
    service_level: float | None = None,
    fabric: bool | None = None,
) -> AsyncIterator[str]:
    """Yield structured JSON events for a full experiment run.

    Modes: sim (scripted rehearsal) · Fabric (real ML in Microsoft Fabric) · local
    (subprocess runner). Real runs default to Fabric when it's configured — the app
    container has no heavy ML (that's why ML lives in Fabric)."""
    from deps import jobs
    from deps import fabric as _fab

    use_fabric = _fab.enabled() if fabric is None else fabric
    fabric_run = (not sim) and use_fabric

    chain = FABRIC_CHAIN if fabric_run else resolve_stages(stages)
    version = _new_version()

    if not jobs.try_acquire_experiment():
        yield _ev(type="error", stage="-", msg="Another experiment is already running. One at a time.")
        return

    yield _ev(type="experiment_start", version=version, cutoff=cutoff,
              mode=("fabric" if fabric_run else ("sim" if sim else "real")),
              stages=[{"id": s, "label": l} for s, l in chain], total=len(chain))
    try:
        if sim:
            async for e in _simulate(chain, cutoff, version, speed):
                yield e
        elif fabric_run:
            async for e in _run_fabric(cutoff):
                yield e
        else:
            params: dict = {}
            if cutoff:
                params["cutoff"] = cutoff
            async for e in _run_real(chain, cutoff, version, params):
                yield e
    finally:
        jobs.release_experiment()
