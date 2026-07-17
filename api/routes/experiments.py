"""
Experiments slice — P3. Leaderboard + version compare + re-run.

Every trained model version lives in models/registry/<ver>/meta.json; the live one is
pointed to by models/champion.json. This slice turns those into first-class, ranked
experiment rows and lets you compare any two or re-run one.

Neutral field mapping (never leak method/metric names to the client):
    wmape              -> error         (lower is better)
    1 - wmape          -> accuracy      (shown as %)
    holdout_cover_p50  -> median_hit    (calibration, ~0.5 ideal)

Endpoints:
  GET  /experiments               -> leaderboard rows, ranked by accuracy desc
  GET  /experiments/{version}     -> one experiment, full (neutralized) detail
  GET  /experiments/compare?a=&b= -> side-by-side + deltas
  POST /experiments/{version}/rerun -> kick a retrain reusing that version's window
"""
from __future__ import annotations
import json
import pathlib
import shutil
from datetime import datetime, timezone
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/experiments", tags=["experiments"])

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
REG = ROOT / "models" / "registry"
CHAMP = ROOT / "models" / "champion.json"
MODELS = ROOT / "models"
BP = ROOT / "data" / "predictions" / "backtest_preds.parquet"
LOG = MODELS / "pipeline_log.jsonl"


def _champion_version() -> str | None:
    from deps import fabric
    if fabric.enabled():
        try:
            r = fabric.q(f"SELECT TOP 1 version FROM {fabric.table('cfc_champion')} ORDER BY created DESC")
            if r:
                return r[0]["version"]
        except Exception:
            pass
    if CHAMP.exists():
        try:
            return json.loads(CHAMP.read_text()).get("version")
        except Exception:
            return None
    return None


def _load_all_fabric() -> list[dict]:
    """Leaderboard rows from the Fabric cfc_model_runs table (latest run per version)."""
    from deps import fabric
    champ = _champion_version()
    seen: dict[str, dict] = {}
    for r in fabric.q(f"SELECT version, cutoff, train_rows, holdout_rows, wmape, "
                      f"holdout_cover_p50, created FROM {fabric.table('cfc_model_runs')} "
                      f"ORDER BY created DESC"):
        v = r.get("version")
        if v in seen:
            continue  # keep newest run per version
        seen[v] = _neutral({
            "version": v, "cutoff": r.get("cutoff"),
            "train_rows": r.get("train_rows"), "holdout_rows": r.get("holdout_rows"),
            "wmape": r.get("wmape"), "holdout_cover_p50": r.get("holdout_cover_p50"),
        }, champ)
    rows = list(seen.values())
    rows.sort(key=lambda r: (r["accuracy"] is not None, r["accuracy"] or 0), reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def _neutral(meta: dict, champion: str | None) -> dict:
    """Registry meta -> client-facing experiment row (no method/metric names)."""
    wmape = meta.get("wmape")
    accuracy = round((1 - wmape) * 100, 1) if isinstance(wmape, (int, float)) else None
    cover = meta.get("holdout_cover_p50")
    return {
        "version": meta.get("version"),
        "trained_on": meta.get("cutoff"),        # window split date
        "train_rows": meta.get("train_rows"),
        "holdout_rows": meta.get("holdout_rows"),
        "accuracy": accuracy,                     # % (higher better)
        "error": round(wmape, 4) if isinstance(wmape, (int, float)) else None,
        "median_hit": round(cover * 100, 1) if isinstance(cover, (int, float)) else None,
        "is_champion": meta.get("version") == champion,
    }


def _load_all() -> list[dict]:
    from deps import fabric
    if fabric.enabled():
        try:
            rows = _load_all_fabric()
            if rows:
                return rows
        except Exception:
            pass  # fall back to local registry
    champ = _champion_version()
    rows: list[dict] = []
    if REG.exists():
        for d in sorted(REG.iterdir()):
            meta_f = d / "meta.json"
            if meta_f.exists():
                try:
                    rows.append(_neutral(json.loads(meta_f.read_text()), champ))
                except Exception:
                    continue
    # rank by accuracy desc (None last)
    rows.sort(key=lambda r: (r["accuracy"] is not None, r["accuracy"] or 0), reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def _typical_units_off() -> float | None:
    """Plain-English signal for the Simple view: the typical daily miss in UNITS
    (mean absolute error of the P50 forecast) from the champion backtest. Honest,
    concrete, no jargon. None when Fabric is off / no backtest."""
    from deps import fabric
    if not fabric.enabled():
        return None
    try:
        r = fabric.q(f"SELECT AVG(ABS(y - p50)) mae FROM {fabric.table('cfc_backtest_preds')}")
        if r and r[0]["mae"] is not None:
            return round(float(r[0]["mae"]), 1)
    except Exception:
        pass
    return None


@router.get("")
def leaderboard():
    rows = _load_all()
    return {"experiments": rows, "champion": _champion_version(), "count": len(rows),
            "champion_units_off": _typical_units_off()}


@router.get("/run")
async def run_full(
    cutoff: str | None = Query(None, description="train window split YYYY-MM-DD"),
    stages: str | None = Query(None, description="comma list of stage ids; empty = full chain"),
    sim: bool = Query(True, description="true = scripted rehearsal (no train/pull); false = real run"),
    speed: float = Query(1.0, ge=0.25, le=8.0, description="sim animation speed"),
    service_level: float | None = Query(None, description="ordering service level 0-1"),
    fabric: bool | None = Query(None, description="real run engine: true=Fabric job, false=local subprocess; default=auto (Fabric when configured)"),
):
    """SSE — run a WHOLE experiment (extract→sync→features→train→backtest→gate→order→
    predict→monitor) as one stream of structured events. Feeds the Run Experiment UI
    (CLI log + stage stepper + live metric cards + training animation).

    Default sim=true is demo-safe (instant, no creds). sim=false runs for real: Fabric
    monthly-batch extract + LightGBM training (~12 min, one at a time)."""
    from services.experiment_run import run_experiment

    async def gen():
        async for chunk in run_experiment(cutoff=cutoff, stages=stages, sim=sim,
                                          speed=speed, service_level=service_level, fabric=fabric):
            yield chunk

    return EventSourceResponse(gen())


@router.get("/compare")
def compare(a: str = Query(...), b: str = Query(...)):
    rows = {r["version"]: r for r in _load_all()}
    if a not in rows or b not in rows:
        missing = [v for v in (a, b) if v not in rows]
        return JSONResponse({"error": f"unknown version(s): {missing}"}, status_code=404)
    ra, rb = rows[a], rows[b]

    def delta(key: str):
        va, vb = ra.get(key), rb.get(key)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            return round(vb - va, 4)
        return None

    return {
        "a": ra,
        "b": rb,
        "deltas": {
            "accuracy": delta("accuracy"),      # + = b more accurate
            "error": delta("error"),            # - = b lower error (better)
            "median_hit": delta("median_hit"),
            "train_rows": delta("train_rows"),
        },
    }


@router.get("/{version}")
def detail(version: str):
    meta_f = REG / version / "meta.json"
    if not meta_f.exists():
        return JSONResponse({"error": f"unknown version: {version}"}, status_code=404)
    meta = json.loads(meta_f.read_text())
    row = _neutral(meta, _champion_version())
    row["feature_count"] = len(meta.get("feats", []))
    return row


# ── full experiment evidence (DS-facing, technical) ─────────────────────────
def _feature_importance(top: int = 12) -> list[dict]:
    try:
        import lightgbm as lgb
        b = lgb.Booster(model_file=(MODELS / "lgbm_p50.txt").as_posix())
        pairs = sorted(zip(b.feature_name(), b.feature_importance(importance_type="gain")),
                       key=lambda x: -x[1])[:top]
        mx = pairs[0][1] or 1
        return [{"name": n, "gain": round(g / mx, 3)} for n, g in pairs]
    except Exception:
        return []


def _run_history(version: str, limit: int = 12) -> list[dict]:
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text().strip().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if version and r.get("version") not in (version, None) and r.get("kind") == "retrain":
            continue
        out.append({
            "kind": r.get("kind"), "ts": r.get("ts"),
            "wmape": r.get("wmape") or r.get("recent_wmape"),
            "note": r.get("verdict") or (f"registered {r.get('version')}" if r.get("kind") == "retrain" else None),
            "drift": bool(r.get("drift")),
        })
    return out[-limit:]


def _f(v, nd=3):
    try:
        return round(float(v), nd)
    except Exception:
        return None


def _evidence_fabric(version: str):
    """Evidence for one version computed live from Fabric cfc_* tables (T-SQL)."""
    from deps import fabric
    meta_rows = fabric.q(
        f"SELECT TOP 1 version, cutoff, train_rows, holdout_rows, wmape, holdout_cover_p50, "
        f"feats, cats FROM {fabric.table('cfc_model_runs')} WHERE version = ? ORDER BY created DESC",
        (version,))
    if not meta_rows:
        return None
    meta = meta_rows[0]
    is_champ = version == _champion_version()
    BT = fabric.table("cfc_backtest_preds")

    o = fabric.q(
        f"SELECT SUM(ABS(y-p50))/NULLIF(SUM(y),0) wmape, SUM(p50-y)/NULLIF(SUM(y),0) bias, "
        f"AVG(CASE WHEN y<=p50 THEN 1.0 ELSE 0 END) c50, AVG(CASE WHEN y<=p85 THEN 1.0 ELSE 0 END) c85, "
        f"AVG(CASE WHEN y<=p95 THEN 1.0 ELSE 0 END) c95, COUNT(*) n FROM {BT}")[0]
    metrics = {
        "wmape": _f(o["wmape"]), "p50_bias": _f(o["bias"]),
        "cover_p50": _f((o["c50"] or 0) * 100, 1), "cover_p85": _f((o["c85"] or 0) * 100, 1),
        "cover_p95": _f((o["c95"] or 0) * 100, 1), "test_rows": int(o["n"] or 0),
    }
    by_class = [{"cls": r["cls"], "wmape": _f(r["wmape"]), "n": int(r["n"])}
                for r in fabric.q(f"SELECT abc cls, SUM(ABS(y-p50))/NULLIF(SUM(y),0) wmape, COUNT(*) n "
                                  f"FROM {BT} GROUP BY abc ORDER BY abc") if r["cls"] is not None]
    folds = [{"fold": r["fold"], "wmape": _f(r["wmape"])}
             for r in fabric.q(f"SELECT fold, SUM(ABS(y-p50))/NULLIF(SUM(y),0) wmape "
                               f"FROM {BT} GROUP BY fold ORDER BY fold")]
    residuals = [{"bin": int(r["bin"]), "n": int(r["n"])}
                 for r in fabric.q(f"SELECT FLOOR(v/5.0)*5 bin, COUNT(*) n FROM "
                                   f"(SELECT CASE WHEN y-p50 < -50 THEN -50 WHEN y-p50 > 50 THEN 50 "
                                   f"ELSE y-p50 END v FROM {BT}) t GROUP BY FLOOR(v/5.0)*5 ORDER BY 1")]
    scatter = [{"actual": _f(r["actual"], 1), "pred": _f(r["pred"], 1)}
               for r in fabric.q(f"SELECT TOP 140 y actual, p50 pred FROM {BT} WHERE y > 0 ORDER BY NEWID()")]
    # Feature importance from the Fabric cfc_feature_importance table (this version;
    # fall back to the latest version present if this one wasn't logged). Tolerant of a
    # missing table (older runs) — leaves the chart empty rather than erroring.
    feat_imp: list[dict] = []
    try:
        FI = fabric.table("cfc_feature_importance")
        fi_rows = fabric.q(f"SELECT TOP 20 feature, gain FROM {FI} WHERE version = ? ORDER BY gain DESC", (version,))
        if not fi_rows:
            fi_rows = fabric.q(f"SELECT TOP 20 feature, gain FROM {FI} "
                               f"WHERE version = (SELECT TOP 1 version FROM {FI} ORDER BY gain DESC) ORDER BY gain DESC")
        feat_imp = [{"name": r["feature"], "gain": _f(r["gain"], 1)} for r in fi_rows]
    except Exception:
        feat_imp = []

    class_a = next((x["wmape"] for x in by_class if x["cls"] == "A"), None)
    feats = (meta.get("feats") or "").split(",") if meta.get("feats") else []
    cats = (meta.get("cats") or "").split(",") if meta.get("cats") else []
    hist = [{"kind": "retrain", "ts": str(r.get("created")), "wmape": _f(r.get("wmape")),
             "note": f"registered {r.get('version')}", "drift": False}
            for r in fabric.q(f"SELECT TOP 8 version, wmape, created FROM {fabric.table('cfc_model_runs')} "
                              f"ORDER BY created DESC")]
    return {
        "version": version, "name": "LightGBM · quantile P50/P85/P95 (Fabric)",
        "status": "ACTIVE · CHAMPION" if is_champ else "challenger", "is_champion": is_champ,
        "cutoff": meta.get("cutoff"), "train_rows": meta.get("train_rows"),
        "holdout_rows": meta.get("holdout_rows"),
        "metrics": {**metrics, "class_a_wmape": class_a, "floor_wmape": 0.401},
        "calibration": [
            {"level": 50, "target": 50.0, "actual": metrics.get("cover_p50")},
            {"level": 85, "target": 85.0, "actual": metrics.get("cover_p85")},
            {"level": 95, "target": 95.0, "actual": metrics.get("cover_p95")},
        ],
        "by_class": by_class, "folds": folds, "residuals": residuals, "scatter": scatter,
        "feature_importance": feat_imp,   # from Fabric cfc_feature_importance
        "hyperparams": {"objective": "quantile", "alphas": "0.5 / 0.85 / 0.95",
                        "num_leaves": 255, "learning_rate": 0.05, "n_estimators": 600,
                        "min_child_samples": 100, "categorical_feature": f"{len(cats)} cols"},
        "feats": feats, "cats": cats, "run_history": hist,
        "note": "Computed live from Fabric cfc_backtest_preds." + ("" if is_champ else
                " Charts reflect the champion backtest."),
    }


@router.get("/{version}/evidence")
def evidence(version: str):
    from deps import fabric
    if fabric.enabled():
        try:
            ev = _evidence_fabric(version)
            if ev:
                return ev
        except Exception:
            pass  # fall back to local parquet path
    """Everything for one experiment: metrics, calibration, feature impact, residuals,
    scatter, accuracy by class/fold, config, run history. Technical (DS-facing).
    Metrics are computed from the champion's walk-forward backtest_preds."""
    meta_f = REG / version / "meta.json"
    if not meta_f.exists():
        return JSONResponse({"error": f"unknown version: {version}"}, status_code=404)
    meta = json.loads(meta_f.read_text())
    is_champ = meta.get("version") == _champion_version()

    metrics, by_class, folds, residuals, scatter = {}, [], [], [], []
    if BP.exists():
        import duckdb
        c = duckdb.connect()
        bp = BP.as_posix()
        o = c.execute(f"""
            SELECT sum(abs(y-p50))/nullif(sum(y),0) wmape,
                   sum(p50-y)/nullif(sum(y),0)      bias,
                   avg(CASE WHEN y<=p50 THEN 1 ELSE 0 END) c50,
                   avg(CASE WHEN y<=p85 THEN 1 ELSE 0 END) c85,
                   avg(CASE WHEN y<=p95 THEN 1 ELSE 0 END) c95,
                   count(*) n
            FROM read_parquet('{bp}')""").fetchone()
        metrics = {
            "wmape": round(o[0], 3), "p50_bias": round(o[1], 3),
            "cover_p50": round(o[2] * 100, 1), "cover_p85": round(o[3] * 100, 1),
            "cover_p95": round(o[4] * 100, 1), "test_rows": o[5],
        }
        by_class = [
            {"cls": r[0], "wmape": round(r[1], 3), "n": r[2]}
            for r in c.execute(f"SELECT abc, sum(abs(y-p50))/nullif(sum(y),0), count(*) "
                               f"FROM read_parquet('{bp}') GROUP BY abc ORDER BY abc").fetchall()
        ]
        folds = [
            {"fold": r[0], "wmape": round(r[1], 3)}
            for r in c.execute(f"SELECT fold, sum(abs(y-p50))/nullif(sum(y),0) "
                               f"FROM read_parquet('{bp}') GROUP BY fold ORDER BY fold").fetchall()
        ]
        residuals = [
            {"bin": int(r[0]), "n": r[1]}
            for r in c.execute(f"WITH r AS (SELECT least(greatest(y-p50,-50),50) d "
                               f"FROM read_parquet('{bp}')) "
                               f"SELECT floor(d/5)*5, count(*) FROM r GROUP BY 1 ORDER BY 1").fetchall()
        ]
        scatter = [
            {"actual": round(r[0], 1), "pred": round(r[1], 1)}
            for r in c.execute(f"SELECT y, p50 FROM read_parquet('{bp}') "
                               f"WHERE y>0 USING SAMPLE 140 ROWS").fetchall()
        ]
        c.close()

    class_a = next((x["wmape"] for x in by_class if x["cls"] == "A"), None)
    return {
        "version": meta.get("version"),
        "name": "LightGBM · quantile P50/P85/P95",
        "status": "ACTIVE · CHAMPION" if is_champ else "challenger",
        "is_champion": is_champ,
        "cutoff": meta.get("cutoff"),
        "train_rows": meta.get("train_rows"),
        "holdout_rows": meta.get("holdout_rows"),
        "metrics": {**metrics, "class_a_wmape": class_a,
                    "floor_wmape": 0.401},   # baseline floor (reports/baselines.md)
        "calibration": [
            {"level": 50, "target": 50.0, "actual": metrics.get("cover_p50")},
            {"level": 85, "target": 85.0, "actual": metrics.get("cover_p85")},
            {"level": 95, "target": 95.0, "actual": metrics.get("cover_p95")},
        ],
        "by_class": by_class,
        "folds": folds,
        "residuals": residuals,
        "scatter": scatter,
        "feature_importance": _feature_importance(),
        "hyperparams": {
            "objective": "quantile", "alphas": "0.5 / 0.85 / 0.95",
            "num_leaves": 255, "learning_rate": 0.05, "n_estimators": 1200,
            "min_child_samples": 50, "feature_fraction": 0.8,
            "categorical_feature": f"{len(meta.get('cats', []))} cols",
        },
        "feats": meta.get("feats", []),
        "cats": meta.get("cats", []),
        "run_history": _run_history(version),
        "note": None if is_champ else "Evidence charts reflect the champion backtest; this version's own backtest is not stored.",
    }


@router.post("/{version}/rerun")
def rerun(version: str):
    """Kick a retrain reusing this version's training window (cutoff).

    Returns a run descriptor the client streams via /pipeline/stream/retrain.
    A retrain registers a NEW versioned experiment and auto-promotes only if it
    beats the champion (champion/challenger gate lives in the engine).
    """
    meta_f = REG / version / "meta.json"
    if not meta_f.exists():
        return JSONResponse({"error": f"unknown version: {version}"}, status_code=404)
    cutoff = json.loads(meta_f.read_text()).get("cutoff")
    return {
        "stage_id": "retrain",
        "reused_from": version,
        "cutoff": cutoff,
        "stream_url": f"/pipeline/stream/retrain?guard=false&cutoff={cutoff}",
    }


@router.post("/{version}/promote")
def promote(version: str):
    """Approve a challenger → make it the live champion (human-in-the-loop gate).

    Fabric mode (USE_FABRIC + trigger configured): fires the notebook MODE=promote,
    PROMOTE_VERSION=<version>, which sets the MLflow champion alias and writes the
    cfc_champion table server-side. Returns a job_id the UI polls via /experiments/jobs/{id}.

    Local mode (no Fabric): points models/champion.json at this version's meta. The
    previous champion is backed up to champion.prev.json so the action is reversible —
    the one-click rollback: promote an older version to revert a bad deploy.
    """
    prev = _champion_version()
    if prev == version:
        return {"ok": True, "version": version, "changed": False, "note": "already live"}

    # Fabric approval gate — trigger the notebook promote job.
    from deps import fabric, fabric_jobs
    if fabric.enabled() and fabric_jobs.configured():
        try:
            job = fabric_jobs.run("promote", {"PROMOTE_VERSION": version})
            try:
                from deps.audit import record_event
                record_event("system:experiments", "promote", f"{prev or 'none'}→{version} (fabric {job['job_id']})")
            except Exception:
                pass
            return {"ok": True, "version": version, "changed": True, "previous": prev,
                    "mode": "fabric", "job_id": job["job_id"],
                    "poll": f"/experiments/jobs/{job['job_id']}",
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        except Exception as e:
            return JSONResponse({"error": f"fabric promote failed: {e}"}, status_code=502)

    # Local file promote (no Fabric).
    meta_f = REG / version / "meta.json"
    if not meta_f.exists():
        return JSONResponse({"error": f"unknown version: {version}"}, status_code=404)
    if CHAMP.exists():
        shutil.copyfile(CHAMP, CHAMP.with_name("champion.prev.json"))
    CHAMP.write_text(meta_f.read_text())
    try:
        from deps.audit import record_event
        record_event("system:experiments", "promote", f"{prev or 'none'}→{version}")
    except Exception:
        pass
    return {"ok": True, "version": version, "changed": True, "previous": prev,
            "mode": "local",
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


@router.post("/{version}/reject")
def reject(version: str):
    """Reject a challenger — record the decision, leave the champion untouched.

    The challenger stays registered (promoted=False) in the Fabric registry for audit;
    this just logs the human 'no'. Non-destructive.
    """
    try:
        from deps.audit import record_event
        record_event("system:experiments", "reject", f"challenger {version} rejected")
    except Exception:
        pass
    return {"ok": True, "version": version, "rejected": True,
            "champion": _champion_version(),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    """Poll a Fabric notebook job (promote / run). Returns status + timing."""
    from deps import fabric_jobs
    if not fabric_jobs.configured():
        return JSONResponse({"error": "fabric jobs not configured"}, status_code=503)
    try:
        return fabric_jobs.status(job_id)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)
